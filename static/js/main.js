$(document).ready(function() {
    // Состояние приложения
    const appState = {
        corpFilterEnabled: true,
        allOrganizations: [],
        currentData: null,
        currentView: 'table',
        isLoading: false
    };

    // Инициализация
    function init() {
        initControls();
        loadOrganizations();
        showEmptyState();
    }

    // Инициализация элементов управления
    function initControls() {
        // Datepicker
        flatpickr(".datepicker", {
            dateFormat: "Y-m-d",
            locale: "ru",
            allowInput: true,
            maxDate: "today"
        });

        // Кнопка выхода
        $("#logoutBtn").click(function() {
            if (confirm("Вы уверены, что хотите выйти?")) {
                window.location.href = "/logout";
            }
        });

        // Переключатель представлений
        $("#tableViewBtn").click(function(e) {
            e.preventDefault();
            if (appState.currentData) {
                switchView('table');
                $(this).blur(); // Убираем фокус
            }
        });

        $("#chartViewBtn").click(function(e) {
            e.preventDefault();
            if (appState.currentData) {
                switchView('chart');
                $(this).blur(); // Убираем фокус
            } else {
                showAlert("Сначала загрузите данные", "warning");
            }
        });

        // Обработчик формы
        $("#filterForm").on("submit", function(e) {
            e.preventDefault();
            loadData();
        });

        // Обработчик кнопки экспорта
        $("#exportBtn").click(function() {
            if (!validateForm()) return;

            const params = {
                organization: $("#organization").val(),
                date_from: $("#dateFrom").val(),
                date_to: $("#dateTo").val(),
                monthly: $("#monthly").is(":checked")
            };

            if (new Date(params.date_from) > new Date(params.date_to)) {
                showAlert("Дата 'с' не может быть позже даты 'по'", "warning");
                return;
            }

            const queryString = new URLSearchParams(params).toString();
            window.location.href = `/api/export?${queryString}`;
        });

        // Переключение фильтра организаций
        $("#toggleCorpFilter").change(function() {
            appState.corpFilterEnabled = $(this).is(":checked");
            loadOrganizations();
        });

        // Автоматическая загрузка при изменении группировки
        $("#monthly").change(function() {
            if ($("#organization").val() && $("#dateFrom").val() && $("#dateTo").val()) {
                loadData();
            }
        });
    }

    // Переключение представлений
    function switchView(view) {
        if (!appState.currentData) {
            showEmptyState();
            return;
        }

        appState.currentView = view;
        $("#tableViewBtn").toggleClass("active", view === 'table');
        $("#chartViewBtn").toggleClass("active", view === 'chart');

        if (view === 'table') {
            $("#tableContainer").show();
            $("#chartContainer").hide();
        } else {
            $("#tableContainer").hide();
            $("#chartContainer").show();
            renderCharts(appState.currentData);
        }
    }

    // Загрузка данных
    function loadData() {
        if (appState.isLoading) return;

        if (!validateForm()) {
            showEmptyState();
            return;
        }

        appState.isLoading = true;
        // Показываем легкую индикацию загрузки
        $("#applyBtn").prop('disabled', true).html('<span class="spinner-border spinner-border-sm" role="status" aria-hidden="true"></span> Загрузка...');

        const params = {
            organization: $("#organization").val(),
            date_from: $("#dateFrom").val(),
            date_to: $("#dateTo").val(),
            monthly: $("#monthly").is(":checked")
        };

        $.get("/api/data", params)
            .done(function(data) {
                appState.currentData = data;
                if (data && data.length > 0) {
                    showData();
                } else {
                    showAlert("Нет данных для отображения", "warning");
                    showEmptyState();
                }
            })
            .fail(function(jqXHR) {
                showAlert(jqXHR.responseJSON?.error || "Ошибка загрузки", "danger");
                showEmptyState();
            })
            .always(function() {
                appState.isLoading = false;
                $("#applyBtn").prop('disabled', false).text('Показать данные');
            });
    }

    // Показать данные
    function showData() {
        $("#emptyState").hide();
        $("#dataContainers").show();
        updateCurrentView();
    }

    // Обновить текущее представление
    function updateCurrentView() {
        if (!appState.currentData) return;

        if (appState.currentView === 'table') {
            $("#tableContainer").show();
            $("#chartContainer").hide();
            updateTable(appState.currentData);
        } else {
            $("#tableContainer").hide();
            $("#chartContainer").show();
            renderCharts(appState.currentData);
        }
    }

    // Пустое состояние
    function showEmptyState() {
        appState.currentData = null;
        $("#emptyState").show();
        $("#dataContainers").hide();

        // Очищаем данные
        $("#dataTable tbody").empty();
        if (typeof Plotly !== 'undefined') {
            Plotly.purge('driversChart');
            Plotly.purge('ordersChart');
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

    // Функция загрузки организаций
    function loadOrganizations() {
        const select = $("#organization");
        select.prop('disabled', true).html('<option value="">Загрузка...</option>');

        $.get("/api/organizations", { filter_corp: appState.corpFilterEnabled })
            .always(() => select.prop('disabled', false))
            .done(function(data) {
                appState.allOrganizations = data;
                updateOrganizationList(data);
                initSearch();
            })
            .fail(function(jqXHR) {
                showAlert("Ошибка загрузки организаций", "danger");
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

        if (select.data('select2')) {
            select.select2('destroy');
            initSearch();
        }
    }

    // Инициализация поиска Select2
    function initSearch() {
        $("#organization").select2({
            placeholder: "Выберите или начните вводить...",
            language: "ru",
            width: '100%',
            minimumInputLength: 0,
            dropdownAutoWidth: true,
            data: appState.allOrganizations.map(org => ({ id: org, text: org })),
            dropdownCssClass: "enhanced-dropdown"
        });

        $("#organization").on('select2:open', function() {
            setTimeout(() => {
                const searchField = document.querySelector('.select2-container--open .select2-search__field');
                if (searchField) searchField.focus();
            }, 50);
        });
    }

    // Функция обновления таблицы
    function updateTable(data) {
        const tbody = $("#dataTable tbody");
        tbody.empty();

        const isMonthly = $("#monthly").is(":checked");

        // Обновляем заголовки
        $("#dataTable thead tr").html(isMonthly ? `
            <th>Месяц</th>
            <th>Организация</th>
            <th>Среднее кол-во водителей</th>
            <th>Выполнено заказов</th>
        ` : `
            <th>Дата</th>
            <th>Организация</th>
            <th>Макс. водителей</th>
            <th>Выполнено заказов</th>
        `);

        data.forEach(item => {
            const date = isMonthly
                ? item.month_name || getRussianMonthName(new Date(item.date))
                : new Date(item.date).toLocaleDateString('ru-RU');

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

    // Функция отрисовки графиков
    function renderCharts(data) {
        if (typeof Plotly === 'undefined') {
            showAlert("Библиотека графиков не загрузилась", "warning");
            switchView('table');
            return;
        }

        if (!data || data.length === 0) {
            showAlert("Нет данных для отображения графиков", "warning");
            return;
        }

        const isMonthly = $("#monthly").is(":checked");

        try {
            // Подготовка данных
            const xValues = data.map(item =>
                isMonthly ? item.month_name : new Date(item.date)
            );

            // График водителей
            Plotly.newPlot('driversChart', [{
                x: xValues,
                y: data.map(item => item.max_drivers),
                type: 'scatter',
                mode: 'lines+markers',
                name: 'Водители',
                marker: { color: '#0d6efd' },
                line: { shape: 'spline' }
            }], {
                title: isMonthly ? 'Среднее количество водителей' : 'Максимальное количество водителей',
                xaxis: {
                    title: isMonthly ? 'Месяц' : 'Дата',
                    type: isMonthly ? 'category' : 'date',
                    tickformat: isMonthly ? '' : '%d.%m.%Y'
                },
                yaxis: { title: 'Количество' },
                margin: { t: 40, b: 100, l: 50, r: 30 },
                hovermode: 'x unified'
            });

            // График заказов
            Plotly.newPlot('ordersChart', [{
                x: xValues,
                y: data.map(item => item.total_orders),
                type: 'scatter',
                mode: 'lines+markers',
                name: 'Заказы',
                marker: { color: '#198754' },
                line: { shape: 'spline' }
            }], {
                title: 'Количество выполненных заказов',
                xaxis: {
                    title: isMonthly ? 'Месяц' : 'Дата',
                    type: isMonthly ? 'category' : 'date',
                    tickformat: isMonthly ? '' : '%d.%m.%Y'
                },
                yaxis: { title: 'Количество' },
                margin: { t: 40, b: 100, l: 50, r: 30 },
                hovermode: 'x unified'
            });

            // Обработчик изменения размера
            $(window).on('resize', function() {
                Plotly.Plots.resize('driversChart');
                Plotly.Plots.resize('ordersChart');
            });

        } catch (error) {
            console.error("Ошибка при отрисовке графиков:", error);
            showAlert("Ошибка при отрисовке графиков", "danger");
            switchView('table');
        }
    }

    // Вспомогательные функции
    function getRussianMonthName(date) {
        const months = [
            'Январь', 'Февраль', 'Март', 'Апрель', 'Май', 'Июнь',
            'Июль', 'Август', 'Сентябрь', 'Октябрь', 'Ноябрь', 'Декабрь'
        ];
        return months[date.getMonth()] + ' ' + date.getFullYear();
    }

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

    // Запуск приложения
    init();
});