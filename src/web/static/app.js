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

// A control marked data-autosubmit submits its form as soon as it changes (e.g. a checklist checkbox).
document.addEventListener("change", function (event) {
    if (event.target.dataset && event.target.dataset.autosubmit !== undefined) {
        event.target.form.submit();
    }
});

// Definition-of-done rows of the version creation form: add, remove (keeping one), Enter adds a row.
document.addEventListener("DOMContentLoaded", function () {
    var rows = document.getElementById("dod-rows");
    if (!rows) {
        return;
    }
    var template = rows.firstElementChild.cloneNode(true);

    // Append an empty criterion row and focus it.
    function addRow() {
        var row = template.cloneNode(true);
        row.querySelector("input").value = "";
        rows.appendChild(row);
        row.querySelector("input").focus();
    }

    document.getElementById("dod-add").addEventListener("click", addRow);

    rows.addEventListener("click", function (event) {
        if (event.target.classList.contains("dod-remove") && rows.children.length > 1) {
            event.target.closest(".dod-row").remove();
        }
    });

    rows.addEventListener("keydown", function (event) {
        if (event.key === "Enter" && event.target.name === "dod") {
            event.preventDefault();
            addRow();
        }
    });
});
