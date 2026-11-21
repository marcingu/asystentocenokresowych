// Cyfrowy asystent ocen okresowych - drobne ułatwienia w przeglądarce.
// System działa także bez tego pliku: wszystkie reguły sprawdza serwer.
(function () {
  "use strict";

  // Kryterium wybrane na jednej liście jest niedostępne na pozostałych (§ 5 ust. 2 rozp. - bez powtórzeń).
  var listy = Array.prototype.slice.call(document.querySelectorAll("select.kryterium"));
  function odswiezListy() {
    var wybrane = listy.map(function (lista) { return lista.value; });
    listy.forEach(function (lista, numer) {
      Array.prototype.forEach.call(lista.options, function (opcja) {
        opcja.disabled = opcja.value !== "" && wybrane.some(function (wartosc, inny) {
          return inny !== numer && wartosc === opcja.value;
        });
      });
    });
  }
  listy.forEach(function (lista) { lista.addEventListener("change", odswiezListy); });
  odswiezListy();

  // Czynności, których nie da się cofnąć, wymagają potwierdzenia.
  Array.prototype.forEach.call(document.querySelectorAll("[data-potwierdz]"), function (przycisk) {
    przycisk.addEventListener("click", function (zdarzenie) {
      if (!window.confirm(przycisk.getAttribute("data-potwierdz"))) {
        zdarzenie.preventDefault();
      }
    });
  });

  // Lokalny model językowy odpowiada kilkanaście-kilkadziesiąt sekund - pokazujemy, że pracuje.
  Array.prototype.forEach.call(document.querySelectorAll("form.czeka-na-model"), function (formularz) {
    formularz.addEventListener("submit", function () {
      var komunikat = formularz.querySelector(".czekanie");
      if (komunikat) { komunikat.hidden = false; }
      Array.prototype.forEach.call(formularz.querySelectorAll("button[type=submit]"), function (przycisk) {
        // Wyłączenie po chwili: wyłączony od razu przycisk nie wysłałby swojej wartości.
        window.setTimeout(function () { przycisk.disabled = true; }, 0);
      });
    });
  });

  // Przykładowe pytania do asystenta.
  Array.prototype.forEach.call(document.querySelectorAll(".wstaw-pytanie"), function (przycisk) {
    przycisk.addEventListener("click", function () {
      var pole = document.getElementById("pytanie");
      if (pole) { pole.value = przycisk.textContent.trim(); pole.focus(); }
    });
  });
})();
