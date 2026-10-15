document.addEventListener('DOMContentLoaded', function () {
    const dialog = document.getElementById('sol-confirm-dialog');
    if (!dialog) return;

    const dialogPanel = dialog.querySelector('.neutral-dialog-panel');
    const title = document.getElementById('sol-confirm-title');
    const message = document.getElementById('sol-confirm-message');
    const cancelButton = document.getElementById('sol-confirm-cancel');
    const acceptButton = document.getElementById('sol-confirm-accept');
    const acceptedForms = new WeakSet();
    let currentAction = null;
    let previousFocus = null;
    let previousBodyOverflow = '';

    function openDialog(options) {
        currentAction = options.action;
        previousFocus = document.activeElement;
        previousBodyOverflow = document.body.style.overflow;
        title.textContent = options.title;
        message.textContent = options.message;
        cancelButton.textContent = options.cancelLabel || 'Seguir revisando';
        acceptButton.textContent = options.acceptLabel || 'Confirmar';
        acceptButton.classList.remove('neutral-dialog-btn-primary', 'neutral-dialog-btn-danger');
        acceptButton.classList.add(options.acceptTone === 'danger'
            ? 'neutral-dialog-btn-danger'
            : 'neutral-dialog-btn-primary');
        dialog.classList.add('is-open');
        dialog.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
        dialogPanel.focus();
    }

    function closeDialog(restoreFocus) {
        dialog.classList.remove('is-open');
        dialog.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = previousBodyOverflow;
        const action = currentAction;
        currentAction = null;
        if (restoreFocus && previousFocus?.focus) previousFocus.focus();
        return action;
    }

    document.querySelectorAll('form[data-confirm-submit]').forEach(function (form) {
        const dateField = form.querySelector('input[name="fecha"]');
        const originalDate = dateField?.value || '';

        form.addEventListener('submit', function (event) {
            if (event.defaultPrevented) return;
            if (acceptedForms.has(form)) {
                acceptedForms.delete(form);
                return;
            }
            if (!form.noValidate && !form.checkValidity()) return;

            event.preventDefault();
            const selectedDate = dateField?.value || '';
            const dateChanged = Boolean(originalDate && selectedDate && selectedDate !== originalDate);
            openDialog({
                action: function () {
                    acceptedForms.add(form);
                    form.requestSubmit(form.querySelector('[type="submit"]'));
                },
                title: dateChanged
                    ? (form.dataset.confirmDateTitle || form.dataset.confirmSubmitTitle)
                    : form.dataset.confirmSubmitTitle,
                message: dateChanged
                    ? (form.dataset.confirmDateMessage || form.dataset.confirmSubmitMessage)
                    : form.dataset.confirmSubmitMessage,
                cancelLabel: 'Seguir editando',
                acceptLabel: dateChanged
                    ? (form.dataset.confirmDateAccept || 'Enviar cambio')
                    : (form.dataset.confirmSubmitAccept || 'Confirmar envío'),
            });
        });
    });

    document.querySelectorAll('[data-confirm-cancel]').forEach(function (link) {
        link.addEventListener('click', function (event) {
            event.preventDefault();
            const destination = link.href;
            openDialog({
                action: function () { window.location.assign(destination); },
                title: link.dataset.confirmCancelTitle || 'Cancelar edición',
                message: link.dataset.confirmCancelMessage || '¿Quieres salir? Los cambios no guardados se perderán.',
                cancelLabel: 'Seguir editando',
                acceptLabel: 'Salir',
                acceptTone: 'danger',
            });
        });
    });

    cancelButton.addEventListener('click', function () { closeDialog(true); });
    acceptButton.addEventListener('click', function () {
        const action = closeDialog(false);
        if (action) action();
    });
    dialog.addEventListener('click', function (event) {
        if (event.target === dialog) closeDialog(true);
    });
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && dialog.classList.contains('is-open')) {
            closeDialog(true);
        }
    });
});
