document.addEventListener('DOMContentLoaded', function () {
    document.querySelectorAll('[data-trajectory-value]').forEach(function (valueInput) {
        const section = valueInput.closest('.sol-section-block');
        const includedPanel = section.querySelector('[data-trajectory-included]');
        const excludedPanel = section.querySelector('[data-trajectory-excluded]');
        if (!includedPanel || !excludedPanel) return;

        section.querySelectorAll('[data-trajectory-toggle]').forEach(function (button) {
            button.addEventListener('click', function () {
                const include = button.dataset.nextValue === 'on';
                valueInput.value = include ? 'on' : '';
                includedPanel.hidden = !include;
                excludedPanel.hidden = include;

                const nextButton = section.querySelector(
                    '[data-trajectory-toggle][data-next-value="' + (include ? '' : 'on') + '"]'
                );
                if (nextButton) nextButton.focus();
            });
        });
    });
});