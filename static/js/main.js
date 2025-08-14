$(document).ready(function() {
    // Состояние фильтра организаций
    let corpFilterEnabled = true;
    let allOrganizations = [];

    // Инициализация datepicker
    flatpickr(".datepicker", {
        dateFormat: "Y-m-d",
        locale: "ru",
        allowInput: true,
        maxDate: "today"
    });

    // Загрузка списка организаций
    loadOrganizations();

    // Обработчик кнопки экспорта
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

    // Обработка формы фильтрации
    $("#filterForm").on("submit", function(e) {
        e.preventDefault();
        if (validateForm()) {
            loadData();
        }
    });

    // Переключение фильтра организаций
    $("#toggleCorpFilter").change(function() {
        corpFilterEnabled = $(this).is(":checked");
        loadOrganizations();
    });

    // Функция загрузки организаций
    function loadOrganizations() {
        const select = $("#organization");
        select.prop('disabled', true).html('<option value="">Загрузка...</option>');

        $.get("/api/organizations", { filter_corp: corpFilterEnabled })
            .always(() => select.prop('disabled', false))
            .done(function(data) {
                allOrganizations = data;
                updateOrganizationList(data);
                initSearch();
            })
            .fail(function(jqXHR) {
                showAlert("Ошибка загрузки организаций", "danger");
            });
    }

    // Инициализация поиска
    function initSearch() {
        $("#organization").select2({
            placeholder: "Выберите или начните вводить...",
            language: "ru",
            width: '100%',
            minimumInputLength: 0,
            dropdownAutoWidth: true,
            data: allOrganizations.map(org => ({ id: org, text: org })),
            dropdownCssClass: "enhanced-dropdown"
        });

        // Добавляем обработчик открытия dropdown
        $("#organization").on('select2:open', function() {
            // Даем небольшой таймаут для гарантии инициализации dropdown
            setTimeout(() => {
                // Находим поле поиска и фокусируем его
                const searchField = document.querySelector('.select2-container--open .select2-search__field');
                if (searchField) {
                    searchField.focus();
                }
            }, 50);
        });
    }

    // Обновление списка организаций
    function updateOrganizationList(organizations) {
        const select = $("#organization");
        select.empty();

        if (organizations.length === 0) {
            select.append('<option value="" disabled>Нет организаций</option>');
            return;
        }

        select.append('<option value="" selected disabled>Выберите организацию</option>');
        organizations.forEach(org => {
            select.append(`<option value="${org}">${org}</option>`);
        });

        // Если Select2 уже инициализирован - обновляем данные
        if ($("#organization").data('select2')) {
            $("#organization").select2('destroy');
            initSearch();
        }
    }

    // Функция валидации формы
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

    // Функция загрузки данных
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

        $("#monthly").change(function() {
            if ($("#organization").val() && $("#dateFrom").val() && $("#dateTo").val()) {
                loadData();
            }
        });

        $.get("/api/data", params)
            .done(function(data) {
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
            });
    }

    // Функция обновления таблицы
    function updateTable(data) {
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

    // Функция показа уведомлений
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
});
