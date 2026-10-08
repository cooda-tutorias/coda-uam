document.addEventListener('DOMContentLoaded', function () {
    const openButton = document.getElementById('open-trayectoria-dialog');
    const dialog = document.getElementById('trayectoria-dialog');
    if (!openButton || !dialog) return;

    const dialogPanel = dialog.querySelector('[role="dialog"]');
    const closeButton = document.getElementById('trayectoria-dialog-close');
    const fileNameLabel = document.getElementById('trayectoria-dialog-file-name');
    const downloadLink = document.getElementById('trayectoria-download-link');
    const newTabLink = document.getElementById('trayectoria-new-tab-link');
    const canvas = document.getElementById('trayectoria-pdf-canvas');
    const canvasWrap = document.getElementById('trayectoria-pdf-canvas-wrap');
    const status = document.getElementById('trayectoria-pdf-status');
    const pageLabel = document.getElementById('trayectoria-pdf-page');
    const previousButton = document.getElementById('trayectoria-pdf-previous');
    const nextButton = document.getElementById('trayectoria-pdf-next');
    const zoomOutButton = document.getElementById('trayectoria-pdf-zoom-out');
    const zoomInButton = document.getElementById('trayectoria-pdf-zoom-in');
    const context = canvas.getContext('2d');

    let pdfDocument = null;
    let currentPage = 1;
    let zoom = 1;
    let pdfjsLibrary = null;
    let renderTask = null;
    let renderToken = 0;
    let previousFocus = null;
    let previousBodyOverflow = '';

    function updateControls() {
        pageLabel.textContent = pdfDocument
            ? 'Página ' + currentPage + ' de ' + pdfDocument.numPages
            : 'Cargando PDF…';
        previousButton.disabled = !pdfDocument || currentPage <= 1;
        nextButton.disabled = !pdfDocument || currentPage >= pdfDocument.numPages;
        zoomOutButton.disabled = !pdfDocument || zoom <= 0.6;
        zoomInButton.disabled = !pdfDocument || zoom >= 2;
    }

    async function renderPage() {
        if (!pdfDocument) return;
        const token = ++renderToken;
        if (renderTask) renderTask.cancel();

        try {
            const pdfPage = await pdfDocument.getPage(currentPage);
            const baseViewport = pdfPage.getViewport({ scale: 1 });
            const availableWidth = Math.max(240, canvasWrap.clientWidth - 24);
            const fitScale = Math.min(1.5, availableWidth / baseViewport.width);
            const scale = fitScale * zoom;
            const viewport = pdfPage.getViewport({ scale: scale });
            const outputScale = window.devicePixelRatio || 1;

            canvas.width = Math.ceil(viewport.width * outputScale);
            canvas.height = Math.ceil(viewport.height * outputScale);
            canvas.style.width = Math.ceil(viewport.width) + 'px';
            canvas.style.height = Math.ceil(viewport.height) + 'px';

            renderTask = pdfPage.render({
                canvasContext: context,
                viewport: viewport,
                transform: outputScale === 1
                    ? null
                    : [outputScale, 0, 0, outputScale, 0, 0],
            });
            await renderTask.promise;
            if (token !== renderToken) return;

            status.textContent = '';
            updateControls();
        } catch (error) {
            if (error.name !== 'RenderingCancelledException') {
                console.error('No se pudo renderizar la página del PDF.', error);
                status.textContent = 'No se pudo mostrar la vista previa. Usa “Abrir en otra pestaña” para consultar el PDF.';
            }
        }
    }

    async function openDialog() {
        previousFocus = document.activeElement;
        previousBodyOverflow = document.body.style.overflow;
        dialog.classList.add('is-open');
        dialog.setAttribute('aria-hidden', 'false');
        document.body.style.overflow = 'hidden';
        dialogPanel.focus();

        const viewUrl = openButton.dataset.viewUrl;
        downloadLink.href = openButton.dataset.downloadUrl;
        newTabLink.href = viewUrl;
        fileNameLabel.textContent = openButton.dataset.fileName;
        status.textContent = 'Cargando vista previa…';
        updateControls();

        if (pdfDocument) {
            await renderPage();
            return;
        }

        try {
            pdfjsLibrary = pdfjsLibrary || await import(
                'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.min.mjs'
            );
            pdfjsLibrary.GlobalWorkerOptions.workerSrc =
                'https://cdnjs.cloudflare.com/ajax/libs/pdf.js/4.10.38/pdf.worker.min.mjs';
            pdfDocument = await pdfjsLibrary.getDocument({ url: viewUrl }).promise;
            currentPage = 1;
            zoom = 1;
            await renderPage();
        } catch (error) {
            console.error('No se pudo cargar la vista previa del PDF.', error);
            status.textContent = 'No se pudo cargar la vista previa. Usa “Abrir en otra pestaña” para consultar el PDF.';
            updateControls();
        }
    }

    function closeDialog() {
        renderToken += 1;
        if (renderTask) {
            renderTask.cancel();
            renderTask = null;
        }
        dialog.classList.remove('is-open');
        dialog.setAttribute('aria-hidden', 'true');
        document.body.style.overflow = previousBodyOverflow;
        if (previousFocus) previousFocus.focus();
    }

    openButton.addEventListener('click', openDialog);
    closeButton.addEventListener('click', closeDialog);
    dialog.addEventListener('click', function (event) {
        if (event.target === dialog) closeDialog();
    });
    document.addEventListener('keydown', function (event) {
        if (event.key === 'Escape' && dialog.classList.contains('is-open')) {
            closeDialog();
        }
    });

    previousButton.addEventListener('click', function () {
        if (!pdfDocument || currentPage <= 1) return;
        currentPage -= 1;
        updateControls();
        renderPage();
    });
    nextButton.addEventListener('click', function () {
        if (!pdfDocument || currentPage >= pdfDocument.numPages) return;
        currentPage += 1;
        updateControls();
        renderPage();
    });
    zoomOutButton.addEventListener('click', function () {
        zoom = Math.max(0.6, Math.round((zoom - 0.2) * 10) / 10);
        renderPage();
    });
    zoomInButton.addEventListener('click', function () {
        zoom = Math.min(2, Math.round((zoom + 0.2) * 10) / 10);
        renderPage();
    });
    window.addEventListener('resize', function () {
        if (pdfDocument && dialog.classList.contains('is-open')) renderPage();
    });
});
