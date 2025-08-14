import re
from contextlib import contextmanager
from io import BytesIO

import pandas as pd
import psycopg2
from dateutil.parser import parse
from flask import Flask, render_template, jsonify, request, make_response

from config import config

app = Flask(__name__, static_folder='static', template_folder='templates')


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
corp_filter_enabled = True


def read_corp_filter():
    try:
        with open(CORP_FILTER_PATH, 'r') as f:
            return [line.strip() for line in f if line.strip()]
    except FileNotFoundError:
        return []


def sanitize_filename(filename):
    """Очищает имя файла от недопустимых символов"""
    filename = re.sub(r'[\\/*?:"<>|]', "", filename)
    return filename.replace(" ", "_")


@app.route('/')
def dashboard():
    return render_template('dashboard.html')


@app.route('/api/organizations')
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


@app.route('/api/toggle-corp-filter', methods=['POST'])
def toggle_corp_filter():
    global corp_filter_enabled
    corp_filter_enabled = not corp_filter_enabled
    return jsonify({'status': 'success', 'filter_enabled': corp_filter_enabled})


@app.route('/api/data')
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

            with conn.cursor() as cur:
                cur.execute(query, params)
                columns = [desc[0] for desc in cur.description]
                data = [dict(zip(columns, row)) for row in cur.fetchall()]

            if not data:
                return jsonify({'error': 'Нет данных для экспорта'}), 404

            df = pd.DataFrame(data)
            df['date'] = pd.to_datetime(df['date'])

            if monthly:
                # Группировка по месяцам
                months_ru = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                             'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
                df = df.groupby(pd.Grouper(key='date', freq='ME')).agg({
                    'max_drivers': 'mean',
                    'total_orders': 'sum'
                }).reset_index()
                df['Период'] = df['date'].dt.month.apply(lambda x: months_ru[x - 1]) + ' ' + df['date'].dt.year.astype(
                    str)
                df_export = df[['Период', 'max_drivers', 'total_orders']].rename(columns={
                    'max_drivers': 'Среднее количество водителей',
                    'total_orders': 'Всего заказов'
                })
                df_export['Организация'] = org
                df_export = df_export[['Период', 'Организация', 'Среднее количество водителей', 'Всего заказов']]
                df_export['Среднее количество водителей'] = df_export['Среднее количество водителей'].round(1)
            else:
                # Дневные данные
                df_export = df.rename(columns={
                    'date': 'Дата',
                    'organization': 'Организация',
                    'max_drivers': 'Максимальное количество водителей',
                    'total_orders': 'Всего заказов'
                })
                df_export['Дата'] = df_export['Дата'].dt.strftime('%d.%m.%Y')

            # Создаем Excel файл с явным указанием параметров
            output = BytesIO()
            with pd.ExcelWriter(
                    output,
                    engine='openpyxl',
                    mode='w'
            ) as writer:
                df_export.to_excel(writer, sheet_name='Данные', index=False)

            output.seek(0)

            # Формируем имя файла
            filename = sanitize_filename(f"export_{org}_{date_from}_{date_to}.xlsx")

            # Отправляем файл
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

    except Exception as e:
        app.logger.error(f"Ошибка экспорта: {str(e)}")
        return jsonify({'error': 'Ошибка сервера при экспорте'}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
