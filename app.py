import re
from contextlib import contextmanager
from io import BytesIO
from functools import wraps

import pandas as pd
import psycopg2
from dateutil.parser import parse
from flask import Flask, render_template, jsonify, request, make_response, session, redirect, url_for

from config import config

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = config.SECRET_KEY


def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)

    return decorated_function


@contextmanager
def db_connection():
    conn = None
    try:
        conn = psycopg2.connect(**config.db_config)
        yield conn
    except Exception as e:
        app.logger.error(f"Database connection error: {e}")
        raise
    finally:
        if conn:
            conn.close()


CORP_FILTER_PATH = 'corp.txt'


def read_corp_filter():
    try:
        with open(CORP_FILTER_PATH, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []


def sanitize_filename(filename):
    """Очищает имя файла от недопустимых символов"""
    try:
        # Транслитерация русских символов
        translit_map = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
            'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
            'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
            'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '',
            'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
            'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'E',
            'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
            'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
            'Ф': 'F', 'Х': 'H', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch',
            'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
        }

        filename = ''.join([translit_map.get(c, c) for c in filename])

        # Удаление недопустимых символов
        filename = re.sub(r'[\\/*?:"<>|]', "", filename)
        filename = re.sub(r'[^\w\-_. ]', '', filename)
        filename = filename.replace(" ", "_")

        # Ограничение длины
        return filename[:100]

    except (TypeError, AttributeError) as e:
        app.logger.warning(f"Filename sanitization warning: {e}")
        return "exported_data.xlsx"


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == config.AUTH_USERNAME and password == config.AUTH_PASSWORD:
            session['logged_in'] = True
            session.permanent = True  # Сессия будет постоянной
            return redirect(url_for('dashboard'))
        else:
            return render_template('login.html', error='Неверные учетные данные')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.pop('logged_in', None)
    return redirect(url_for('login'))


@app.route('/')
@login_required
def dashboard():
    return render_template('dashboard.html')


@app.route('/api/organizations')
@login_required
def get_organizations():
    try:
        filter_corp = request.args.get('filter_corp', 'true') == 'true'
        corp_prefixes = read_corp_filter() if filter_corp else []

        with db_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT DISTINCT organization FROM organization_daily_stats ORDER BY organization")
                organizations = [row[0] for row in cur.fetchall()]

                if filter_corp and corp_prefixes:
                    organizations = [org for org in organizations
                                     if any(org.startswith(prefix) for prefix in corp_prefixes)]

                return jsonify(organizations)
    except Exception as e:
        app.logger.error(f"Ошибка при получении организаций: {e}")
        return jsonify([])


@app.route('/api/data')
@login_required
def get_data():
    try:
        # Получаем параметры из request
        org = request.args.get('organization', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        monthly = request.args.get('monthly', 'false') == 'true'

        # Проверка обязательных параметров
        if not org:
            return jsonify({'error': 'Не выбрана организация'}), 400

        if not date_from or not date_to:
            return jsonify({'error': 'Не выбран период'}), 400

        with db_connection() as conn:
            query = """
                SELECT date, organization, max_drivers, total_orders 
                FROM organization_daily_stats
                WHERE organization = %s AND date BETWEEN %s AND %s
                ORDER BY date
            """
            params = [org, parse(date_from).date(), parse(date_to).date()]

            with conn.cursor() as cur:
                cur.execute(query, params)
                columns = [desc[0] for desc in cur.description]
                data = [dict(zip(columns, row)) for row in cur.fetchall()]

            if monthly and data:
                df = pd.DataFrame(data)
                df['date'] = pd.to_datetime(df['date'])
                grouped = df.groupby(pd.Grouper(key='date', freq='ME'))

                # Рассчитываем среднее и проверяем на целое число
                def safe_mean(x):
                    avg = x.mean()
                    return int(avg) if avg.is_integer() else round(avg, 1)

                df = grouped.agg({
                    'max_drivers': safe_mean,  # Используем нашу функцию
                    'total_orders': 'sum'
                }).reset_index()
                df['organization'] = org

                # Русские названия месяцев с заглавной буквы
                months_ru = {
                    1: 'Январь', 2: 'Февраль', 3: 'Март',
                    4: 'Апрель', 5: 'Май', 6: 'Июнь',
                    7: 'Июль', 8: 'Август', 9: 'Сентябрь',
                    10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
                }
                df['month_name'] = df['date'].dt.month.map(months_ru) + ' ' + df['date'].dt.year.astype(str)
                data = df.to_dict('records')

            return jsonify(data)

    except Exception as e:
        app.logger.error(f"Ошибка при получении данных: {e}")
        return jsonify({'error': str(e)}), 500


@app.route('/api/export')
@login_required
def export_data():
    try:
        # Получаем параметры
        org = request.args.get('organization', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        monthly = request.args.get('monthly', 'false').lower() == 'true'

        if not org or not date_from or not date_to:
            return jsonify({'error': 'Необходимые параметры не указаны'}), 400

        with db_connection() as conn:
            # Базовый запрос
            query = """
                SELECT date, organization, max_drivers, total_orders 
                FROM organization_daily_stats
                WHERE organization = %s AND date BETWEEN %s AND %s
                ORDER BY date
            """
            params = [org, parse(date_from).date(), parse(date_to).date()]

            try:
                with conn.cursor() as cur:
                    cur.execute(query, params)
                    columns = [desc[0] for desc in cur.description]
                    data = [dict(zip(columns, row)) for row in cur.fetchall()]
            except psycopg2.Error as db_error:
                app.logger.error(f"Database error during export: {db_error}")
                return jsonify({'error': 'Ошибка базы данных'}), 500

            if not data:
                return jsonify({'error': 'Нет данных для экспорта'}), 404

            try:
                df = pd.DataFrame(data)
                df['date'] = pd.to_datetime(df['date'])
            except (ValueError, KeyError) as df_error:
                app.logger.error(f"Data processing error: {df_error}")
                return jsonify({'error': 'Ошибка обработки данных'}), 500

            # Создаем Excel файл в памяти
            output = BytesIO()

            try:
                from openpyxl import Workbook
                from openpyxl.utils.dataframe import dataframe_to_rows
                from openpyxl.styles import Font, Alignment

                wb = Workbook()
                ws = wb.active
                ws.title = "Данные"

                if monthly:
                    months_ru = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                                 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
                    try:
                        df = df.groupby(pd.Grouper(key='date', freq='ME')).agg({
                            'max_drivers': 'mean',
                            'total_orders': 'sum'
                        }).reset_index()
                    except Exception as group_error:
                        app.logger.error(f"Grouping error: {group_error}")
                        return jsonify({'error': 'Ошибка группировки данных'}), 500

                    headers = ["Период", "Организация", "Среднее количество водителей", "Всего заказов"]
                    ws.append(headers)

                    for _, row in df.iterrows():
                        try:
                            month_name = months_ru[row['date'].month - 1] + ' ' + str(row['date'].year)
                            ws.append([
                                month_name,
                                org,
                                round(float(row['max_drivers']), 1),
                                int(row['total_orders'])
                            ])
                        except (ValueError, IndexError) as row_error:
                            app.logger.error(f"Row processing error: {row_error}")
                            continue

                else:
                    headers = ["Дата", "Организация", "Максимальное количество водителей", "Всего заказов"]
                    ws.append(headers)

                    for _, row in df.iterrows():
                        try:
                            ws.append([
                                row['date'].strftime('%d.%m.%Y'),
                                row['organization'],
                                float(row['max_drivers']),
                                int(row['total_orders'])
                            ])
                        except (ValueError, KeyError) as row_error:
                            app.logger.error(f"Row processing error: {row_error}")
                            continue

                # Форматирование
                bold_font = Font(bold=True)
                for cell in ws[1]:
                    cell.font = bold_font
                    cell.alignment = Alignment(horizontal='center')

                # Автоподбор ширины колонок
                for column in ws.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            cell_value = str(cell.value) if cell.value is not None else ""
                            if len(cell_value) > max_length:
                                max_length = len(cell_value)
                        except Exception as cell_error:
                            app.logger.debug(f"Cell processing warning: {cell_error}")
                            continue
                    adjusted_width = (max_length + 2) * 1.2
                    ws.column_dimensions[column_letter].width = adjusted_width

                wb.save(output)
                output.seek(0)

            except Exception as excel_error:
                app.logger.error(f"Excel generation error: {excel_error}")
                return jsonify({'error': 'Ошибка создания Excel файла'}), 500

            try:
                filename = sanitize_filename(f"export_{org}_{date_from}_{date_to}.xlsx")
                response = make_response(output.getvalue())
                response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
                response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
                return response
            except Exception as response_error:
                app.logger.error(f"Response creation error: {response_error}")
                return jsonify({'error': 'Ошибка формирования ответа'}), 500

    except Exception as e:
        app.logger.error(f"Unexpected export error: {e}", exc_info=True)
        return jsonify({'error': 'Неожиданная ошибка при экспорте'}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
