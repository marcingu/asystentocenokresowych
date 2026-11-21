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
  // Komunikat wpisujemy do elementu role="status", który jest w stronie od początku: tylko taką zmianę
  // czytnik ekranu ogłasza (WCAG 4.1.3). Elementu odkrytego razem z gotową treścią zwykle nie ogłasza.
  function pokazCzekanie(komunikat) {
    if (komunikat) { komunikat.textContent = komunikat.getAttribute("data-komunikat") || ""; }
  }
  Array.prototype.forEach.call(document.querySelectorAll("form.czeka-na-model"), function (formularz) {
    formularz.addEventListener("submit", function () {
      pokazCzekanie(formularz.querySelector(".czekanie"));
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

  // Przycisk wywołujący model w formularzu, który ma też inne przyciski: komunikat tylko po jego kliknięciu.
  Array.prototype.forEach.call(document.querySelectorAll("button[data-czekanie]"), function (przycisk) {
    przycisk.addEventListener("click", function () {
      pokazCzekanie(document.getElementById(przycisk.getAttribute("data-czekanie")));
    });
  });

  // Projekt przygotowany przez model trafia do formularza dopiero po decyzji człowieka - i nadal nie jest zapisany.
  Array.prototype.forEach.call(document.querySelectorAll("button[data-wstaw-z]"), function (przycisk) {
    przycisk.addEventListener("click", function () {
      var zrodlo = document.getElementById(przycisk.getAttribute("data-wstaw-z"));
      var cel = document.getElementById(przycisk.getAttribute("data-wstaw-do"));
      if (!zrodlo || !cel) { return; }
      var dotychczas = cel.value.replace(/\s+$/, "");
      cel.value = dotychczas ? dotychczas + "\n\n" + zrodlo.value : zrodlo.value;
      cel.focus();
    });
  });

  // Po powrocie strony z projektem (albo komunikatem asystenta) pokazujemy od razu to miejsce.
  var projekt = document.getElementById("projekt-ai");
  if (projekt && projekt.scrollIntoView) { projekt.scrollIntoView({ block: "center" }); }
})();
