(function () {
  'use strict';

  // line letter + color mapping
  var LINE_MAP = {
    'COMMUTER LINE BOGOR': { letter: 'B', color: '#E30A16' },
    'COMMUTER LINE CIKARANG': { letter: 'C', color: '#0072CE' },
    'COMMUTER LINE RANGKASBITUNG': { letter: 'R', color: '#00A650' },
    'COMMUTER LINE TANGERANG': { letter: 'T', color: '#F7941D' },
    'COMMUTER LINE TANJUNGPRIUK': { letter: 'P', color: '#DD0067' }
  };

  function lineInfo(lineName) {
    return LINE_MAP[lineName] || { letter: '?', color: '#888' };
  }

  function createCircle(lineName, size) {
    var info = lineInfo(lineName);
    var el = document.createElement('span');
    el.className = 'line-circle line-circle--' + size;
    el.style.backgroundColor = info.color;
    el.textContent = info.letter;
    return el;
  }

  function minutesUntil(timeStr) {
    var parts = timeStr.split(':');
    var h = parseInt(parts[0], 10);
    var m = parseInt(parts[1], 10);
    var now = new Date();
    var nowMinutes = now.getHours() * 60 + now.getMinutes();
    var targetMinutes = h * 60 + m;
    var diff = targetMinutes - nowMinutes;
    if (diff < -180) diff += 1440;
    return diff;
  }

  // recents in localStorage
  var RECENTS_KEY = 'kommute_recents';
  var MAX_RECENTS = 3;

  function getRecents() {
    try {
      return JSON.parse(localStorage.getItem(RECENTS_KEY)) || [];
    } catch (e) {
      return [];
    }
  }

  function saveRecent(code, name) {
    var recents = getRecents().filter(function (r) { return r.code !== code; });
    recents.unshift({ code: code, name: name });
    if (recents.length > MAX_RECENTS) recents = recents.slice(0, MAX_RECENTS);
    localStorage.setItem(RECENTS_KEY, JSON.stringify(recents));
  }

  // DOM refs
  var searchInput = document.getElementById('search');
  var recentsDiv = document.getElementById('recents');
  var resultsDiv = document.getElementById('results');
  var picker = document.getElementById('picker');
  var board = document.getElementById('board');
  var stationNameEl = document.getElementById('station-name');
  var arrivalsDiv = document.getElementById('arrivals');
  var backBtn = document.getElementById('back-btn');

  // state
  var allStations = [];
  var refreshTimer = null;

  // build flat station list from grouped API response
  function buildStationList(apiLines) {
    var map = {};
    apiLines.forEach(function (line) {
      line.stations.forEach(function (s) {
        if (!map[s.code]) {
          map[s.code] = { code: s.code, name: s.name, lines: [] };
        }
        map[s.code].lines.push({ name: line.name, color: line.color });
      });
    });
    return Object.keys(map).map(function (k) { return map[k]; })
      .sort(function (a, b) { return a.name.localeCompare(b.name); });
  }

  // fetch stations on load
  fetch('/api/stations')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      allStations = buildStationList(data.lines);
      renderRecents();
    });

  // search filtering
  searchInput.addEventListener('input', function () {
    var query = searchInput.value.trim().toLowerCase();
    if (!query) {
      resultsDiv.textContent = '';
      renderRecents();
      return;
    }
    recentsDiv.textContent = '';
    var matches = allStations.filter(function (s) {
      return s.name.toLowerCase().indexOf(query) !== -1;
    });
    renderResults(matches);
  });

  function renderResults(stations) {
    resultsDiv.textContent = '';
    stations.forEach(function (s) {
      var row = document.createElement('div');
      row.className = 'result-row';

      var circles = document.createElement('div');
      circles.className = 'result-circles';
      s.lines.forEach(function (line) {
        circles.appendChild(createCircle(line.name, 'lg'));
      });
      row.appendChild(circles);

      var name = document.createElement('span');
      name.className = 'result-name';
      name.textContent = s.name;
      row.appendChild(name);

      row.addEventListener('click', function () {
        showBoard(s.code, s.name);
      });

      resultsDiv.appendChild(row);
    });
  }

  function renderRecents() {
    recentsDiv.textContent = '';
    var recents = getRecents();
    if (recents.length === 0) return;

    recents.forEach(function (r) {
      var chip = document.createElement('button');
      chip.className = 'recent-chip';
      chip.textContent = r.name;
      chip.addEventListener('click', function () {
        showBoard(r.code, r.name);
      });
      recentsDiv.appendChild(chip);
    });
  }

  // navigation
  function showBoard(code, name) {
    saveRecent(code, name);
    picker.hidden = true;
    board.hidden = false;
    stationNameEl.textContent = name;
    searchInput.value = '';
    resultsDiv.textContent = '';
    loadArrivals(code);
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(function () { loadArrivals(code); }, 60000);
  }

  backBtn.addEventListener('click', function () {
    board.hidden = true;
    picker.hidden = false;
    if (refreshTimer) clearInterval(refreshTimer);
    renderRecents();
  });

  function loadArrivals(code) {
    fetch('/api/stations/' + encodeURIComponent(code) + '/arrivals')
      .then(function (r) { return r.json(); })
      .then(function (data) {
        renderArrivals(data.arrivals || []);
      });
  }

  function renderArrivals(arrivals) {
    arrivalsDiv.textContent = '';

    if (arrivals.length === 0) {
      var noData = document.createElement('div');
      noData.className = 'no-data';
      noData.textContent = 'no upcoming trains';
      arrivalsDiv.appendChild(noData);
      return;
    }

    arrivals.forEach(function (a) {
      var mins = minutesUntil(a.arrival_time);

      var row = document.createElement('div');
      row.className = 'arrival-row';

      var left = document.createElement('div');
      left.className = 'arrival-left';

      var line1 = document.createElement('div');
      line1.className = 'arrival-line1';
      line1.appendChild(createCircle(a.line, 'sm'));

      var dest = document.createElement('span');
      dest.className = 'arrival-dest';
      dest.textContent = a.destination;
      line1.appendChild(dest);

      left.appendChild(line1);

      if (a.via) {
        var via = document.createElement('div');
        via.className = 'arrival-via';
        via.textContent = a.via;
        left.appendChild(via);
      }

      row.appendChild(left);

      var right = document.createElement('div');
      right.className = 'arrival-right';

      var cd = document.createElement('div');
      cd.className = 'countdown';
      if (mins <= 0) {
        cd.classList.add('arriving');
        cd.textContent = 'now';
      } else if (mins <= 5) {
        cd.classList.add('soon');
        cd.textContent = mins + ' min';
      } else if (mins > 60) {
        cd.textContent = a.arrival_time.substring(0, 5);
      } else {
        cd.textContent = mins + ' min';
      }
      right.appendChild(cd);

      var absTime = document.createElement('div');
      absTime.className = 'abs-time';
      absTime.textContent = a.arrival_time.substring(0, 5);
      right.appendChild(absTime);

      row.appendChild(right);
      arrivalsDiv.appendChild(row);
    });
  }

  // refresh countdowns every 30s without refetching
  setInterval(function () {
    if (!board.hidden) {
      var rows = arrivalsDiv.querySelectorAll('.arrival-row');
      rows.forEach(function (row) {
        var absTime = row.querySelector('.abs-time');
        if (!absTime) return;
        var timeStr = absTime.textContent + ':00';
        var mins = minutesUntil(timeStr);
        var cd = row.querySelector('.countdown');
        if (!cd) return;

        cd.className = 'countdown';
        if (mins <= 0) {
          cd.classList.add('arriving');
          cd.textContent = 'now';
        } else if (mins <= 5) {
          cd.classList.add('soon');
          cd.textContent = mins + ' min';
        } else if (mins > 60) {
          cd.textContent = absTime.textContent;
        } else {
          cd.textContent = mins + ' min';
        }
      });
    }
  }, 30000);
})();
