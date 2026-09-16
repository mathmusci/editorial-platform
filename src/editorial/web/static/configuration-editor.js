const editor = document.querySelector(".configuration-editor");
if (editor) {
  const markUnsaved = () => {
    document.getElementById("draft-status").textContent = "Unsaved draft";
    const activate = editor.querySelector('button[value="use"]');
    if (activate) activate.disabled = true;
  };
  editor.addEventListener("input", markUnsaved);
  editor.addEventListener("change", markUnsaved);
}
