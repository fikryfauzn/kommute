(function () {
  'use strict';

  var lineSelect = document.getElementById('line-select');
  var stationSelect = document.getElementById('station-select');
  var goBtn = document.getElementById('go-btn');
  var picker = document.getElementById('picker');
  var board = document.getElementById('board');
  var stationName = document.getElementById('station-name');
  var arrivalsDiv = document.getElementById('arrivals');
  var backBtn = document.getElementById('back-btn');

  var linesData = [];
  var refreshTimer = null;

  fetch('/api/stations')
    .then(function (r) { return r.json(); })
    .then(function (data) {
      linesData = data.lines;
      linesData.forEach(function (line) {
        var opt = document.createElement('option');
        opt.value = line.name;
        opt.textContent = line.name.replace('COMMUTER LINE ', '');
        opt.style.color = line.color;
        lineSelect.appendChild(opt);
      });
    });

  lineSelect.addEventListener('change', function () {
    stationSelect.textContent = '';
    var blank = document.createElement('option');
    blank.value = '';
    blank.textContent = '-- pick station --';
    stationSelect.appendChild(blank);
    stationSelect.disabled = true;
    goBtn.disabled = true;

    var line = linesData.find(function (l) { return l.name === lineSelect.value; });
    if (!line) return;

    line.stations.forEach(function (s) {
      var opt = document.createElement('option');
      opt.value = s.code;
      opt.textContent = s.name;
      stationSelect.appendChild(opt);
    });
    stationSelect.disabled = false;
  });

  stationSelect.addEventListener('change', function () {
    goBtn.disabled = !stationSelect.value;
  });

  goBtn.addEventListener('click', function () {
    var code = stationSelect.value;
    var name = stationSelect.options[stationSelect.selectedIndex].textContent;
    showBoard(code, name);
  });

  backBtn.addEventListener('click', function () {
    board.hidden = true;
    picker.hidden = false;
    if (refreshTimer) clearInterval(refreshTimer);
  });

  function showBoard(code, name) {
    picker.hidden = true;
    board.hidden = false;
    stationName.textContent = name;
    loadArrivals(code);
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(function () { loadArrivals(code); }, 60000);
  }

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

      var dot = document.createElement('span');
      dot.className = 'line-dot';
      dot.style.backgroundColor = a.color;
      left.appendChild(dot);

      var destText = a.destination;
      if (a.via) destText += ' via ' + a.via;

      var destEl = document.createElement('span');
      destEl.className = 'arrival-dest';
      destEl.textContent = destText;
      left.appendChild(destEl);

      row.appendChild(left);

      var right = document.createElement('div');
      right.className = 'train-time';

      var cd = document.createElement('div');
      cd.className = 'countdown';
      if (mins <= 0) {
        cd.classList.add('arriving');
        cd.textContent = 'now';
      } else if (mins <= 5) {
        cd.classList.add('soon');
        cd.textContent = mins + ' min';
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

  // refresh countdowns every 30s without refetching
  setInterval(function () {
    if (!board.hidden) {
      var rows = arrivalsDiv.querySelectorAll('.train-row');
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
        } else {
          cd.textContent = mins + ' min';
        }
      });
    }
  }, 30000);
})();
