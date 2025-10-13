document.addEventListener("DOMContentLoaded", () => {
  fetch("news.html")
    .then(response => response.text())
    .then(html => {
      document.getElementById("news-feed").insertAdjacentHTML("beforeend", html);
    })
    .catch(error => {
      console.error("Ошибка загрузки новостей:", error);
    });
});