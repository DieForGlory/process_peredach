// /app/cadastre_process/static/js/deals_list.js

document.addEventListener('DOMContentLoaded', function() {

    // -------------------------------------------------------------------
    // ОБЩАЯ ФУНКЦИЯ ДЛЯ ОБРАБОТКИ ВСЕХ ЧЕКБОКСОВ
    // -------------------------------------------------------------------
    function handleCheckboxChange(checkbox, url) {
        const dealId = checkbox.dataset.dealId;
        if (!dealId) {
            console.error('Deal ID is missing from checkbox data attribute!');
            return;
        }
        checkbox.disabled = true;

        fetch(url, { method: 'POST' })
        .then(response => {
            if (!response.ok) throw new Error('Server error');
            return response.json();
        })
        .then(data => {
            if (data.status === 'success') {
                // Перезагружаем страницу, чтобы сервер отрисовал новое состояние
                window.location.reload();
            } else {
                alert('Произошла ошибка при сохранении. Попробуйте снова.');
                checkbox.checked = false;
                checkbox.disabled = false;
            }
        })
        .catch(error => {
            console.error('Fetch Error:', error);
            alert('Произошла сетевая ошибка.');
            checkbox.checked = false;
            checkbox.disabled = false;
        });
    }

    // -------------------------------------------------------------------
    // ПРИВЯЗКА ОБРАБОТЧИКОВ К ЧЕКБОКСАМ
    // -------------------------------------------------------------------
    document.querySelectorAll('.delivery-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', () => handleCheckboxChange(
            checkbox,
            `/mark-delivered/${checkbox.dataset.dealId}`
        ));
    });

    document.querySelectorAll('.client-arrived-checkbox').forEach(checkbox => {
        checkbox.addEventListener('change', () => handleCheckboxChange(
            checkbox,
            `/mark-arrived/${checkbox.dataset.dealId}`
        ));
    });

    // -------------------------------------------------------------------
    // ЛОГИКА ДЛЯ ТАЙМЕРА И СКРЫТИЯ КОЛОНКИ
    // -------------------------------------------------------------------
    const timerHeader = document.getElementById('timer-header');

    function updateTimers() {
        document.querySelectorAll('.countdown-timer').forEach(span => {
            const deadline = new Date(span.dataset.deadline);
            if (isNaN(deadline)) return; // Пропускаем, если дата невалидна

            const now = new Date();
            const diff = deadline - now;

            if (diff < 0) {
                span.textContent = "Время вышло";
                span.classList.add('text-danger');
            } else {
                const days = Math.floor(diff / (1000 * 60 * 60 * 24));
                const hours = Math.floor((diff % (1000 * 60 * 60 * 24)) / (1000 * 60 * 60));
                const minutes = Math.floor((diff % (1000 * 60 * 60)) / (1000 * 60));
                const seconds = Math.floor((diff % (1000 * 60)) / 1000);
                span.textContent = `${days}д ${hours.toString().padStart(2, '0')}:${minutes.toString().padStart(2, '0')}:${seconds.toString().padStart(2, '0')}`;
            }
        });
    }

    function toggleTimerColumn() {
        const isHidden = timerHeader.classList.toggle('hidden');
        document.querySelectorAll('.timer-cell').forEach(cell => {
            cell.classList.toggle('hidden', isHidden);
        });
        localStorage.setItem('timerColumnHidden', isHidden);
    }

    if (timerHeader) {
        timerHeader.addEventListener('click', toggleTimerColumn);

        if (localStorage.getItem('timerColumnHidden') === 'true') {
            toggleTimerColumn();
        }

        if (document.querySelector('.countdown-timer')) {
            updateTimers();
            setInterval(updateTimers, 1000);
        }
    }
});
document.querySelectorAll('.download-acceptance-act-btn').forEach(button => {
    button.addEventListener('click', function(event) {
        event.preventDefault(); // Предотвращаем стандартное действие
        const downloadUrl = this.dataset.url;

        // Меняем текст и блокируем кнопку, чтобы показать, что что-то происходит
        this.disabled = true;
        this.textContent = 'Загрузка...';

        // Запускаем скачивание файла
        window.location.href = downloadUrl;

        // Добавляем небольшую задержку (чтобы дать файлу начать скачиваться)
        // и затем принудительно перезагружаем страницу.
        setTimeout(function() {
            window.location.reload();
        }, 2000); // 2 секунды
    });
});