// /app/static/js/deals_list.js

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
    // ЛОГИКА ДЛЯ КНОПКИ СКАЧИВАНИЯ АКТА
    // -------------------------------------------------------------------
    document.querySelectorAll('.download-acceptance-act-btn').forEach(button => {
        button.addEventListener('click', function(event) {
            event.preventDefault();
            const downloadUrl = this.dataset.url;
            this.disabled = true;
            this.textContent = 'Загрузка...';
            window.location.href = downloadUrl;
            setTimeout(() => window.location.reload(), 2000);
        });
    });

    // -------------------------------------------------------------------
    // ЛОГИКА ДЛЯ ТАЙМЕРА И СКРЫТИЯ КОЛОНКИ
    // -------------------------------------------------------------------
    const timerHeader = document.getElementById('timer-header');
    function updateTimers() {
        document.querySelectorAll('.countdown-timer').forEach(span => {
            const deadline = new Date(span.dataset.deadline);
            if (isNaN(deadline)) return;
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

    if (timerHeader) {
        if (document.querySelector('.countdown-timer')) {
            updateTimers();
            setInterval(updateTimers, 1000);
        }
    }

    // -------------------------------------------------------------------
    // ЛОГИКА ДЛЯ МОДАЛЬНОГО ОКНА ПРИЕМКИ
    // -------------------------------------------------------------------
    const acceptanceModal = document.getElementById('acceptanceModal');
    if (acceptanceModal) {
        const modalDealIdInput = document.getElementById('modal-deal-id');
        const form = document.getElementById('acceptance-form');

        document.querySelectorAll('.open-acceptance-modal').forEach(button => {
            button.addEventListener('click', function() {
                modalDealIdInput.value = this.dataset.dealId;
                form.reset();
            });
        });

        document.getElementById('save-acceptance-results').addEventListener('click', async function() {
            const dealId = modalDealIdInput.value;
            const isSigned = form.elements['is_signed'].value;
            const hasDefects = form.elements['has_defects'].value;

            if (!isSigned || !hasDefects) {
                alert('Пожалуйста, ответьте на все вопросы.');
                return;
            }

            this.disabled = true;
            this.textContent = 'Сохранение...';

            try {
                // 1. Отправляем информацию о подписи и дефектах
                await fetch(`/process-acceptance/${dealId}`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        is_signed: (isSigned === 'true'),
                        has_defects: (hasDefects === 'true')
                    })
                });

                // 2. Загружаем файлы (если они есть)
                const filesData = new FormData();
                const signedActFile = document.getElementById('signed_act').files[0];
                const defectListFile = document.getElementById('defect_list').files[0];
                let filesAttached = false;

                if (signedActFile) {
                    filesData.append('signed_act', signedActFile);
                    filesAttached = true;
                }
                if (defectListFile) {
                    filesData.append('defect_list', defectListFile);
                    filesAttached = true;
                }

                if (filesAttached) {
                    await fetch(`/upload-final-docs/${dealId}`, {
                        method: 'POST',
                        body: filesData
                    });
                }

                window.location.reload();

            } catch (error) {
                console.error('Error saving acceptance results:', error);
                alert('Произошла ошибка при сохранении данных.');
                this.disabled = false;
                this.textContent = 'Сохранить';
            }
        });
    }
});