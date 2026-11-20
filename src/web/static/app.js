/*
 * Nexus behaviour shared by every page.
 */

// Pressing "c" outside a text field focuses the capture box; Ctrl/Cmd/Alt+C (e.g. copy) are left alone.
document.addEventListener("keydown", function (event) {
    var target = event.target;
    var typing = target.tagName === "INPUT" || target.tagName === "TEXTAREA" || target.isContentEditable;
    var modified = event.ctrlKey || event.metaKey || event.altKey;
    if (!typing && !modified && event.key === "c") {
        event.preventDefault();
        document.getElementById("capture").focus();
    }
});

// A button guarded by an input with data-confirm="<value>" is enabled only once that exact value is typed.
document.addEventListener("input", function (event) {
    var input = event.target;
    if (input.dataset && input.dataset.confirm !== undefined) {
        var button = input.form.querySelector('button[type="submit"]');
        button.disabled = input.value !== input.dataset.confirm;
    }
});

// A button with data-reveal="<id>" shows or hides the element with that id (e.g. the reason
// field of the WAITING icon on a kanban card), focusing its first text field when shown.
document.addEventListener("click", function (event) {
    var button = event.target.closest("[data-reveal]");
    if (button) {
        var target = document.getElementById(button.dataset.reveal);
        target.hidden = !target.hidden;
        button.setAttribute("aria-expanded", String(!target.hidden));
        if (!target.hidden) {
            target.querySelector('input[type="text"]').focus();
        }
    }
});
