$(document).ready(function() {

    // Инициализация datepicker
    flatpickr(".datepicker", {
        dateFormat: "Y-m-d",
        locale: "ru",
        allowInput: true,
        maxDate: "today"
    });

    // Загрузка списка организаций
    loadOrganizations();

    $("#exportBtn").click(function() {
        if (!validateForm()) return;

        const params = {
            organization: $("#organization").val(),
            date_from: $("#dateFrom").val(),
            date_to: $("#dateTo").val(),
            monthly: $("#monthly").is(":checked")
        };

        // Проверка периода
        if (new Date(params.date_from) > new Date(params.date_to)) {
            showAlert("Дата 'с' не может быть позже даты 'по'", "warning");
            return;
        }

        // Формируем URL для экспорта
        const queryString = new URLSearchParams(params).toString();
        window.location.href = `/api/export?${queryString}`;
    });

    // Обработка формы
    $("#filterForm").on("submit", function(e) {
    e.preventDefault();
        if (validateForm()) {
            loadData();
        }
    });
});

        function validateForm() {
            if (!$("#organization").val()) {
                showAlert("Выберите организацию", "warning");
                return false;
            }
            if (!$("#dateFrom").val() || !$("#dateTo").val()) {
                showAlert("Выберите период", "warning");
                return false;
            }
            return true;
        }

        function loadOrganizations() {
            const select = $("#organization");
            select.prop('disabled', true).html('<option value="">Загрузка...</option>');

            $.get("/api/organizations")
                .always(() => select.prop('disabled', false))
                .done(function(data) {
                    const select = $("#organization");
                    select.empty().append('<option value="" selected disabled>Выберите организацию</option>');
                    data.forEach(org => {
                        select.append(`<option value="${org}">${org}</option>`);
                    });
                })
                .fail(function(jqXHR) {
                    showAlert("Ошибка загрузки организаций", "danger");
                })

        }

        function loadData() {

            const params = {
                organization: $("#organization").val(),
                date_from: $("#dateFrom").val(),
                date_to: $("#dateTo").val(),
                monthly: $("#monthly").is(":checked")
            };

            // Проверка периода
            if (new Date(params.date_from) > new Date(params.date_to)) {
                showAlert("Дата 'с' не может быть позже даты 'по'", "warning");
                return;
            }

            console.log("Отправка запроса с параметрами:", params);

            $("#monthly").change(function() {
                if ($("#organization").val() && $("#dateFrom").val() && $("#dateTo").val()) {
                    loadData();
                }
            });

            $.get("/api/data", params)
                .done(function(data) {
                    console.log("Получены данные:", data);

                    if (!data || data.length === 0) {
                        showAlert("Нет данных для отображения", "warning");
                        $("#emptyState").show();
                        $("#tableContainer").hide();
                        return;
                    }

                    $("#emptyState").hide();
                    $("#tableContainer").show();
                    updateTable(data);
                })
                .fail(function(jqXHR, textStatus, errorThrown) {
                    console.error("Ошибка запроса:", textStatus, errorThrown, jqXHR.responseText);
                    const errorMsg = jqXHR.responseJSON?.error || "Ошибка загрузки данных";
                    showAlert(errorMsg, "danger");
                })
        }

        function updateTable(data) {
            console.log("Обновление таблицы с данными:", data);
            const tbody = $("#dataTable tbody");
            tbody.empty();

            const isMonthly = $("#monthly").is(":checked");

            // Обновляем заголовки
            if (isMonthly) {
                $("#dataTable thead tr").html(`
                    <th>Месяц</th>
                    <th>Организация</th>
                    <th>Среднее кол-во водителей</th>
                    <th>Выполнено заказов</th>
                `);
            } else {
                $("#dataTable thead tr").html(`
                    <th>Дата</th>
                    <th>Организация</th>
                    <th>Макс. водителей</th>
                    <th>Выполнено заказов</th>
                `);
            }

            data.forEach(item => {
                // Форматирование даты/месяца
                const date = isMonthly
                    ? item.month_name || getRussianMonthName(new Date(item.date))
                    : new Date(item.date).toLocaleDateString('ru-RU');

                // Форматирование числа водителей (без .0 для целых чисел)
                const drivers = formatNumber(item.max_drivers);
                const orders = formatNumber(item.total_orders);

                tbody.append(`
                    <tr>
                        <td>${date}</td>
                        <td>${item.organization}</td>
                        <td>${drivers}</td>
                        <td>${orders}</td>
                    </tr>
                `);
            });
        }

        // Вспомогательная функция для русских названий месяцев
        function getRussianMonthName(date) {
            const months = [
                'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
                'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
            ];
            return months[date.getMonth()] + ' ' + date.getFullYear();
        }

        // Форматирование чисел (убираем .0 для целых значений)
        function formatNumber(num) {
            if (!num && num !== 0) return '0';
            const fixedNum = Number(num).toFixed(1);
            return fixedNum.endsWith('.0') ? fixedNum.split('.')[0] : fixedNum;
        }

        function showAlert(message, type) {
            const alert = $(`
                <div class="alert alert-${type} alert-dismissible fade show"
                     style="position: fixed; top: 20px; right: 20px; z-index: 1100;">
                    ${message}
                    <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
                </div>
            `);

            $("body").append(alert);

            setTimeout(() => {
                alert.alert('close');
            }, 5000);
        }