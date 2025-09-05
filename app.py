import re
import logging
from contextlib import contextmanager
from io import BytesIO
from functools import wraps
from werkzeug.utils import secure_filename
import pandas as pd
import psycopg2
from dateutil.parser import parse
from flask import Flask, render_template, jsonify, request, make_response, session, redirect, url_for

from config import config

logging.basicConfig(
    level=logging.INFO if not config.DEBUG else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('app.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

app = Flask(__name__, static_folder='static', template_folder='templates')
app.secret_key = config.SECRET_KEY


@app.after_request
def add_security_headers(response):
    if not config.DEBUG:
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['X-Frame-Options'] = 'DENY'
        response.headers['X-XSS-Protection'] = '1; mode=block'
    return response


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
        logger.warning("Corp filter file not found")
        return []
    except Exception as e:
        logger.error(f"Error reading corp filter: {e}")
        return []


def sanitize_filename(filename):
    try:
        translit_map = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'e',
            'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
            'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
            'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch', 'ъ': '',
            'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
        }
        filename = ''.join([translit_map.get(c.lower(), c) for c in filename])
        # Удалим кавычки и другие запрещенные
        filename = re.sub(r'[\\/*?:"<>|\'`]', '', filename)
        filename = re.sub(r'[^\w\-_. ]', '', filename)
        filename = filename.replace(" ", "_")
        return filename[:100]
    except Exception as e:
        logger.warning(f"Filename sanitization warning: {e}")
        return "exported_data.xlsx"


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == config.AUTH_USERNAME and password == config.AUTH_PASSWORD:
            session['logged_in'] = True
            session.permanent = True
            logger.info(f"Successful login from {request.remote_addr}")
            return redirect(url_for('dashboard'))
        else:
            logger.warning(f"Failed login attempt from {request.remote_addr}")
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
        logger.error(f"Ошибка при получении организаций: {e}")
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500


@app.route('/api/data')
@login_required
def get_data():
    try:
        org = request.args.get('organization', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        monthly = request.args.get('monthly', 'false') == 'true'

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

                def safe_mean(x):
                    avg = x.mean()
                    return int(avg) if avg.is_integer() else round(avg, 1)

                df = grouped.agg({
                    'max_drivers': safe_mean,
                    'total_orders': 'sum'
                }).reset_index()
                df['organization'] = org

                months_ru = {
                    1: 'Январь', 2: 'Февраль', 3: 'Март', 4: 'Апрель', 5: 'Май', 6: 'Июнь',
                    7: 'Июль', 8: 'Август', 9: 'Сентябрь', 10: 'Октябрь', 11: 'Ноябрь', 12: 'Декабрь'
                }
                df['month_name'] = df['date'].dt.month.map(months_ru) + ' ' + df['date'].dt.year.astype(str)
                data = df.to_dict('records')

            return jsonify(data)

    except Exception as e:
        logger.error(f"Ошибка при получении данных: {e}")
        return jsonify({'error': 'Внутренняя ошибка сервера'}), 500


@app.route('/api/export')
@login_required
def export_data():
    try:
        org = request.args.get('organization', '')
        date_from = request.args.get('date_from', '')
        date_to = request.args.get('date_to', '')
        monthly = request.args.get('monthly', 'false').lower() == 'true'

        if not org or not date_from or not date_to:
            return jsonify({'error': 'Необходимые параметры не указаны'}), 400

        with db_connection() as conn:
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
                logger.error(f"Database error during export: {db_error}")
                return jsonify({'error': 'Ошибка базы данных'}), 500

            if not data:
                return jsonify({'error': 'Нет данных для экспорта'}), 404

            try:
                df = pd.DataFrame(data)
                df['date'] = pd.to_datetime(df['date'])
            except Exception as df_error:
                logger.error(f"Data processing error: {df_error}")
                return jsonify({'error': 'Ошибка обработки данных'}), 500

            output = BytesIO()

            try:
                from openpyxl import Workbook
                from openpyxl.styles import Font, Alignment

                wb = Workbook()
                ws = wb.active
                ws.title = "Данные"

                if monthly:
                    months_ru = ['Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                                 'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь']
                    df = df.groupby(pd.Grouper(key='date', freq='ME')).agg({
                        'max_drivers': 'mean',
                        'total_orders': 'sum'
                    }).reset_index()

                    headers = ["Период", "Организация", "Среднее количество водителей", "Всего заказов"]
                    ws.append(headers)

                    for _, row in df.iterrows():
                        month_name = months_ru[row['date'].month - 1] + ' ' + str(row['date'].year)
                        ws.append([
                            month_name,
                            org,
                            round(float(row['max_drivers']), 1),
                            int(row['total_orders'])
                        ])
                else:
                    headers = ["Дата", "Организация", "Максимальное количество водителей", "Всего заказов"]
                    ws.append(headers)

                    for _, row in df.iterrows():
                        ws.append([
                            row['date'].strftime('%d.%m.%Y'),
                            row['organization'],
                            float(row['max_drivers']),
                            int(row['total_orders'])
                        ])

                bold_font = Font(bold=True)
                for cell in ws[1]:
                    cell.font = bold_font
                    cell.alignment = Alignment(horizontal='center')

                for column in ws.columns:
                    max_length = 0
                    column_letter = column[0].column_letter
                    for cell in column:
                        try:
                            cell_value = str(cell.value) if cell.value is not None else ""
                            if len(cell_value) > max_length:
                                max_length = len(cell_value)
                        except:
                            continue
                    adjusted_width = (max_length + 2) * 1.2
                    ws.column_dimensions[column_letter].width = adjusted_width

                wb.save(output)
                output.seek(0)

            except Exception as excel_error:
                logger.error(f"Excel generation error: {excel_error}")
                return jsonify({'error': 'Ошибка создания Excel файла'}), 500

            filename = sanitize_filename(f"export_{org}_{date_from}_{date_to}.xlsx")
            filename = secure_filename(filename)
            response = make_response(output.getvalue())
            response.headers['Content-Type'] = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            response.headers['Content-Disposition'] = f'attachment; filename="{filename}"'
            return response

    except Exception as e:
        logger.error(f"Unexpected export error: {e}", exc_info=True)
        return jsonify({'error': 'Неожиданная ошибка при экспорте'}), 500


if __name__ == '__main__':
    logger.info(f"Starting application in {'DEBUG' if config.DEBUG else 'PRODUCTION'} mode")
    app.run(host=config.HOST, port=config.PORT, debug=config.DEBUG)

