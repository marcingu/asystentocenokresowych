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

  var wydzial = document.getElementById("id_wydzial");
  var szefKomorki = document.getElementById("szef-komorki");
  if (wydzial && szefKomorki) {
    function pokazSzefa() {
      var opcja = wydzial.options[wydzial.selectedIndex];
      szefKomorki.textContent = (opcja && opcja.dataset.szef) || "Wybierz komórkę organizacyjną.";
    }
    wydzial.addEventListener("change", pokazSzefa);
    pokazSzefa();
  }

  // W formularzu kadr data mianowania automatycznie wybiera rodzaj zatrudnienia.
  var mianowanie = document.getElementById("id_data_mianowania");
  var rodzaj = document.getElementById("id_rodzaj_zatrudnienia");
  if (mianowanie && rodzaj) {
    function odswiezMianowanie() {
      if (mianowanie.value) { rodzaj.value = "mianowanie"; }
      var wymagane = rodzaj.value === "mianowanie";
      mianowanie.required = wymagane;
      document.getElementById("id_stopien_sluzbowy").required = wymagane;
      document.getElementById("id_data_stopnia").required = wymagane;
    }
    mianowanie.addEventListener("input", odswiezMianowanie);
    rodzaj.addEventListener("change", odswiezMianowanie);
    odswiezMianowanie();
  }

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
      // Źródłem jest pole tekstowe albo lista: z listy bierzemy pozycje oznaczone data-tresc, po jednej w wierszu.
      var tekst = typeof zrodlo.value === "string" ? zrodlo.value : Array.prototype.map.call(
        zrodlo.querySelectorAll("[data-tresc]"), function (pozycja) { return "- " + pozycja.textContent.trim(); }
      ).join("\n");
      var dotychczas = cel.value.replace(/\s+$/, "");
      cel.value = dotychczas ? dotychczas + "\n\n" + tekst : tekst;
      cel.focus();
    });
  });

  // Po powrocie strony z odpowiedzią modelu (albo komunikatem asystenta) pokazujemy od razu to miejsce.
  var wynik = document.getElementById("projekt-ai") || document.getElementById("sugestia-ai") ||
    document.getElementById("rozmowa-ai");
  if (wynik && wynik.scrollIntoView) { wynik.scrollIntoView({ block: "center" }); }
})();
