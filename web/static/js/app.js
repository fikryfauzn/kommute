(function () {
  'use strict';

  /* =========================================================
     CONFIG + STATE
     ========================================================= */

  var LINE_LETTERS = {
    'COMMUTER LINE BOGOR': 'B',
    'COMMUTER LINE CIKARANG': 'C',
    'COMMUTER LINE RANGKASBITUNG': 'R',
    'COMMUTER LINE TANGERANG': 'T',
    'COMMUTER LINE TANJUNGPRIUK': 'P'
  };

  var DEFAULT_COLOR = '#777777';
  var RECENTS_KEY = 'kommute_recents';
  var MAX_RECENTS = 3;

  var TICK_MS = 15000;      // clocks + countdowns
  var REFRESH_MS = 60000;   // arrivals refetch
  var MAX_ARRIVALS = 5;     // rows shown, unfiltered or filtered

  var lineColors = {};
  var allStations = [];
  var activeStation = null;
  var refreshTimer = null;
  var selectedLine = null;   // line name, or null = all lines
  var lastArrivals = [];     // raw API result for the active station


  /* =========================================================
     DOM
     ========================================================= */

  var $ = function (id) { return document.getElementById(id); };

  var picker = $('picker');
  var board = $('board');
  var searchInput = $('search');
  var recentsEl = $('recents');
  var resultsEl = $('results');
  var listLabel = $('station-list-label');
  var homeClock = $('home-clock');
  var boardClock = $('board-clock');
  var stationNameEl = $('station-name');
  var stationLinesEl = $('station-lines');
  var arrivalsEl = $('arrivals');
  var backBtn = $('back-btn');

  /** Create an element: el('div', 'class-a class-b', 'text') */
  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function showMessage(container, text) {
    container.textContent = '';
    container.appendChild(el('div', 'no-data', text));
  }


  /* =========================================================
     LINE BADGES
     ========================================================= */

  function registerLines(lines) {
    lines.forEach(function (line) {
      lineColors[line.name] = line.color || DEFAULT_COLOR;
    });
  }

  function createCircle(lineName, color) {
    var circle = el('span', 'line-circle');
    circle.appendChild(el('span', 'line-letter', LINE_LETTERS[lineName] || '?'));
    circle.style.backgroundColor = color || lineColors[lineName] || DEFAULT_COLOR;
    circle.title = lineName;
    return circle;
  }

  /**
   * Fill a .badges container. With `dense`, 3+ badges overlap
   * (see .badges[data-dense] in CSS) to fit a fixed-width column.
   */
  function renderBadges(container, lines, dense) {
    container.textContent = '';

    lines.forEach(function (line) {
      container.appendChild(createCircle(line.name, line.color));
    });

    if (dense && lines.length > 2) {
      container.dataset.dense = '';
      container.style.setProperty('--n', lines.length);
    } else {
      delete container.dataset.dense;
      container.style.removeProperty('--n');
    }
  }


  /* =========================================================
     LINE FILTER (board header)
     Stations with 2+ lines get toggleable badges: tap one to show
     only that line, tap it again to show everything.
     ========================================================= */

  function renderLineFilter(lines) {
    // single-line station: nothing to filter, plain badge
    if (lines.length < 2) {
      renderBadges(stationLinesEl, lines, false);
      stationLinesEl.removeAttribute('data-filtering');
      return;
    }

    stationLinesEl.textContent = '';
    stationLinesEl.removeAttribute('data-filtering');

    lines.forEach(function (line) {
      var button = el('button', 'line-toggle');
      button.type = 'button';
      button.dataset.line = line.name;
      button.setAttribute('aria-pressed', 'false');
      button.setAttribute('aria-label', line.name);
      button.appendChild(createCircle(line.name, line.color));
      button.addEventListener('click', function () { selectLine(line.name); });
      stationLinesEl.appendChild(button);
    });
  }

  function selectLine(name) {
    selectedLine = selectedLine === name ? null : name;
    syncLineFilter();
    if (activeStation) loadArrivals(activeStation.code);
  }

  function syncLineFilter() {
    stationLinesEl.toggleAttribute('data-filtering', selectedLine !== null);

    stationLinesEl.querySelectorAll('.line-toggle').forEach(function (button) {
      button.setAttribute(
        'aria-pressed',
        String(button.dataset.line === selectedLine)
      );
    });
  }


  /* =========================================================
     JAKARTA TIME
     ========================================================= */

  var clockFormat = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Jakarta',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23'
  });

  function jakartaMinutes() {
    var hour = 0;
    var minute = 0;

    clockFormat.formatToParts(new Date()).forEach(function (part) {
      if (part.type === 'hour') hour = parseInt(part.value, 10);
      if (part.type === 'minute') minute = parseInt(part.value, 10);
    });

    return hour * 60 + minute;
  }

  function updateClocks() {
    var now = clockFormat.format(new Date());
    homeClock.textContent = now;
    boardClock.textContent = now;
  }

  function minutesUntil(timeStr) {
    var parts = timeStr.split(':');
    var target = parseInt(parts[0], 10) * 60 + parseInt(parts[1], 10);
    var diff = target - jakartaMinutes();

    // The service day runs until ~03:00, so a schedule time that looks
    // far in the past is really after midnight.
    if (diff < -180) diff += 1440;

    return diff;
  }


  /* =========================================================
     RECENTS
     ========================================================= */

  function getRecents() {
    try {
      return JSON.parse(localStorage.getItem(RECENTS_KEY)) || [];
    } catch (error) {
      return [];
    }
  }

  function saveRecent(code, name) {
    var recents = getRecents().filter(function (r) { return r.code !== code; });
    recents.unshift({ code: code, name: name });

    try {
      localStorage.setItem(
        RECENTS_KEY,
        JSON.stringify(recents.slice(0, MAX_RECENTS))
      );
    } catch (error) {
      /* storage unavailable (private mode / quota): recents are optional */
    }
  }

  function renderRecents() {
    recentsEl.textContent = '';

    getRecents().forEach(function (recent) {
      var station = findStation(recent.code);
      if (!station) return;

      var chip = el('button', 'recent-chip', station.name);
      chip.type = 'button';
      chip.addEventListener('click', function () { showBoard(station); });
      recentsEl.appendChild(chip);
    });
  }


  /* =========================================================
     STATIONS
     ========================================================= */

  function buildStationList(apiLines) {
    var map = {};

    apiLines.forEach(function (line) {
      line.stations.forEach(function (station) {
        if (!map[station.code]) {
          map[station.code] = {
            code: station.code,
            name: station.name,
            lines: []
          };
        }
        map[station.code].lines.push({ name: line.name, color: line.color });
      });
    });

    return Object.keys(map)
      .map(function (key) { return map[key]; })
      .sort(function (a, b) { return a.name.localeCompare(b.name); });
  }

  function findStation(code) {
    return allStations.find(function (s) { return s.code === code; });
  }

  function buildChevron() {
    var svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'result-arrow');
    svg.setAttribute('viewBox', '0 0 7 12');
    svg.setAttribute('fill', 'none');
    svg.setAttribute('stroke', 'currentColor');
    svg.setAttribute('stroke-width', '1.1');
    svg.setAttribute('aria-hidden', 'true');

    var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', 'M.8 .8 6.2 6 .8 11.2');
    svg.appendChild(path);

    return svg;
  }

  function buildStationRow(station) {
    var row = el('div', 'result-row');
    row.tabIndex = 0;
    row.setAttribute('role', 'button');

    var badges = el('div', 'badges');
    renderBadges(badges, station.lines, true);

    row.appendChild(badges);
    row.appendChild(el('span', 'result-name', station.name));
    row.appendChild(buildChevron());

    function open() { showBoard(station); }

    row.addEventListener('click', open);
    row.addEventListener('keydown', function (event) {
      if (event.key === 'Enter' || event.key === ' ') {
        event.preventDefault();
        open();
      }
    });

    return row;
  }

  function renderStations(stations) {
    resultsEl.textContent = '';

    if (stations.length === 0) {
      showMessage(resultsEl, 'No stations found');
      return;
    }

    var fragment = document.createDocumentFragment();
    stations.forEach(function (station) {
      fragment.appendChild(buildStationRow(station));
    });
    resultsEl.appendChild(fragment);
  }


  /* =========================================================
     SEARCH
     ========================================================= */

  searchInput.addEventListener('input', function () {
    var query = searchInput.value.trim().toLowerCase();

    if (!query) {
      listLabel.textContent = 'ALL STATIONS';
      renderStations(allStations);
      return;
    }

    listLabel.textContent = 'SEARCH RESULTS';

    renderStations(allStations.filter(function (station) {
      return (
        station.name.toLowerCase().includes(query) ||
        station.code.toLowerCase().includes(query)
      );
    }));
  });


  /* =========================================================
     NAVIGATION
     ========================================================= */

  function scrollTop() {
    window.scrollTo({ top: 0, behavior: 'instant' });
  }

  function stopRefresh() {
    if (refreshTimer) {
      clearInterval(refreshTimer);
      refreshTimer = null;
    }
  }

  function showBoard(station) {
    activeStation = station;
    saveRecent(station.code, station.name);

    picker.hidden = true;
    board.hidden = false;

    stationNameEl.textContent = station.name;
    selectedLine = null;
    lastArrivals = [];
    renderLineFilter(station.lines);
    arrivalsEl.textContent = '';

    updateClocks();
    loadArrivals(station.code);

    stopRefresh();
    refreshTimer = setInterval(function () {
      if (activeStation) loadArrivals(activeStation.code);
    }, REFRESH_MS);

    scrollTop();
  }

  function showPicker() {
    activeStation = null;
    stopRefresh();

    board.hidden = true;
    picker.hidden = false;

    searchInput.value = '';
    listLabel.textContent = 'ALL STATIONS';

    renderRecents();
    renderStations(allStations);
    scrollTop();
  }

  backBtn.addEventListener('click', showPicker);


  /* =========================================================
     ARRIVALS
     ========================================================= */

  function loadArrivals(code) {
    var line = selectedLine;
    var url = '/api/stations/' + encodeURIComponent(code) + '/arrivals';
    if (line) url += '?line=' + encodeURIComponent(line);

    fetch(url)
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        // drop responses for a station or filter the user has since left
        if (!activeStation || activeStation.code !== code) return;
        if (selectedLine !== line) return;
        renderArrivals(data.arrivals || []);
      })
      .catch(function (error) {
        console.error('failed to load arrivals', error);
        showMessage(arrivalsEl, 'Unable to load departures');
      });
  }

  function renderArrivals(arrivals) {
    lastArrivals = arrivals;
    paintArrivals();
  }

  /**
   * The API already filters by ?line= and caps at 5. The filter below is
   * only a safety net for an older backend that ignores the parameter.
   */
  function paintArrivals() {
    var visible = lastArrivals
      .filter(function (arrival) {
        return !selectedLine || arrival.line === selectedLine;
      })
      .slice(0, MAX_ARRIVALS);

    arrivalsEl.textContent = '';

    if (visible.length === 0) {
      showMessage(
        arrivalsEl,
        selectedLine
          ? 'No upcoming departures on this line'
          : 'No upcoming departures'
      );
      return;
    }

    var fragment = document.createDocumentFragment();
    visible.forEach(function (arrival) {
      fragment.appendChild(buildArrivalRow(arrival));
    });
    arrivalsEl.appendChild(fragment);
  }

  /**
   * Three children = three grid columns, all vertically centred:
   * [badge] [destination + via] [countdown + clock time]
   */
  function buildArrivalRow(arrival) {
    var row = el('div', 'arrival-grid arrival-row');
    row.dataset.arrivalTime = arrival.arrival_time;

    var text = el('div', 'arrival-text');
    text.appendChild(el('div', 'arrival-dest', arrival.destination));
    if (arrival.via) {
      text.appendChild(el('div', 'arrival-via', 'VIA ' + arrival.via));
    }

    var right = el('div', 'arrival-right');
    right.appendChild(el('div', 'countdown'));
    right.appendChild(el('div', 'abs-time', arrival.arrival_time.slice(0, 5)));

    row.appendChild(createCircle(arrival.line, arrival.color));
    row.appendChild(text);
    row.appendChild(right);

    updateCountdown(row);
    return row;
  }


  /* =========================================================
     COUNTDOWN
     ========================================================= */

  function updateCountdown(row) {
    var timeStr = row.dataset.arrivalTime;
    var countdown = row.querySelector('.countdown');
    if (!timeStr || !countdown) return;

    var minutes = minutesUntil(timeStr);

    countdown.className = 'countdown';

    if (minutes <= 0) {
      countdown.classList.add('urgent');
      countdown.textContent = 'NOW';
      return;
    }

    if (minutes <= 5) countdown.classList.add('urgent');
    else if (minutes <= 15) countdown.classList.add('soon');

    countdown.textContent =
      minutes > 60 ? timeStr.slice(0, 5) : minutes + ' min';
  }

  function refreshCountdowns() {
    arrivalsEl.querySelectorAll('.arrival-row').forEach(updateCountdown);
  }


  /* =========================================================
     INIT
     ========================================================= */

  function loadStations() {
    fetch('/api/stations')
      .then(function (response) {
        if (!response.ok) throw new Error('HTTP ' + response.status);
        return response.json();
      })
      .then(function (data) {
        registerLines(data.lines);
        allStations = buildStationList(data.lines);
        renderRecents();
        renderStations(allStations);
      })
      .catch(function (error) {
        console.error('failed to load stations', error);
        showMessage(resultsEl, 'Unable to load stations');
      });
  }

  updateClocks();
  setInterval(function () {
    updateClocks();
    refreshCountdowns();
  }, TICK_MS);

  loadStations();
})();
