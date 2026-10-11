(function () {
  'use strict';

  // Same product flow as the existing Kommute UI:
  // station picker -> station departures -> back.
  // Board presentation and interactions come from the supplied prototype.

  var LINE_LETTERS = {
    'COMMUTER LINE BOGOR': 'B',
    'COMMUTER LINE CIKARANG': 'C',
    'COMMUTER LINE RANGKASBITUNG': 'R',
    'COMMUTER LINE TANGERANG': 'T',
    'COMMUTER LINE TANJUNGPRIUK': 'P'
  };

  // Only actual railway junctions expose TOWARD directions.
  // Direction definitions and schedules come from /cues.forks, which is
  // classified using each train's physical next stop, not its destination.
  var FORK_STATIONS = new Set(['MRI', 'KPB', 'JNG', 'CTA', 'DU', 'THB']);

  var RECENTS_KEY = 'kommute_recents';
  var MAX_RECENTS = 3;
  var REFRESH_MS = 60000;
  var CLOCK_MS = 15000;
  var MAX_ROWS = 5;

  var stations = [];
  var stationByCode = new Map();
  var currentStation = null;
  var currentLine = null;       // Full backend name, not the line letter.
  var currentDirection = null;  // Stable physical-corridor key.
  var directionGroups = [];
  var flatDepartures = [];
  var cueByTrain = new Map();
  var directionHistory = [];
  var refreshTimer = null;
  var requestVersion = 0;
  var desktopMode = window.matchMedia('(min-width:900px)');
  var selectedTrain = undefined; // default first train; null means deliberately collapsed
  var routeCache = new Map();


  function $(id) { return document.getElementById(id); }

  var picker = $('picker');
  var board = $('board');
  var search = $('search');
  var results = $('results');
  var listLabel = $('station-list-label');
  var recents = $('recents');
  var list = $('list');
  var badges = $('badges');
  var grid = $('grid');
  var dirs = $('dirs');
  var clearButton = $('clear');
  var idle = $('idle');

  function el(tag, className, text) {
    var node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = text;
    return node;
  }

  function empty(container, message) {
    container.replaceChildren(el('div', 'empty', message));
  }

  function lineLetter(fullName) { return LINE_LETTERS[fullName] || '?'; }

  function badge(letter, color, className) {
    var node = el('span', className || 'sb', letter);
    node.style.backgroundColor = color || '#777777';
    return node;
  }

  function toMinutes(hhmm) {
    var parts = hhmm.split(':');
    return Number(parts[0]) * 60 + Number(parts[1]);
  }

  var jakartaClock = new Intl.DateTimeFormat('en-GB', {
    timeZone: 'Asia/Jakarta',
    hour: '2-digit', minute: '2-digit', hourCycle: 'h23'
  });

  function nowMinutes() { return toMinutes(jakartaClock.format(new Date())); }

  // Minutes since the 03:00 service-day boundary, not midnight.
  function serviceSortNow() { return (nowMinutes() + 1440 - 180) % 1440; }

  function cueKey(trainID, arrivalTime) {
    return String(trainID) + '|' + String(arrivalTime).slice(0, 5);
  }

  function minutesAway(time) {
    // Calculate using the same 03:00–02:59 service-day ordering as the Go API.
    // This avoids treating 23:40 as tomorrow's train after midnight.
    var departureSort = (toMinutes(time) + 1440 - 180) % 1440;
    return departureSort - serviceSortNow();
  }

  function etaLabel(time) {
    var minutes = minutesAway(time);
    if (minutes < 0) return 'DEPARTED';
    return minutes === 0 ? 'NOW' : minutes + ' min';
  }

  function showClock() { $('home-clock').textContent = jakartaClock.format(new Date()); }

  async function getJSON(url) {
    var response = await fetch(url);
    if (!response.ok) throw new Error(url + ': HTTP ' + response.status);
    return response.json();
  }

  // ---------------------------------------------------------
  // STATION PICKER (existing Kommute functionality)
  // ---------------------------------------------------------

  function saveRecent(station) {
    try {
      var saved = JSON.parse(localStorage.getItem(RECENTS_KEY) || '[]');
      if (!Array.isArray(saved)) saved = [];
      saved = saved.filter(function (item) { return item.code !== station.code; });
      saved.unshift({ code: station.code, name: station.name });
      localStorage.setItem(RECENTS_KEY, JSON.stringify(saved.slice(0, MAX_RECENTS)));
    } catch (error) { /* Optional storage. */ }
  }

  function recentStations() {
    try {
      var saved = JSON.parse(localStorage.getItem(RECENTS_KEY) || '[]');
      return Array.isArray(saved) ? saved : [];
    } catch (error) { return []; }
  }

  function renderRecents() {
    recents.replaceChildren();
    recentStations().forEach(function (item) {
      var station = stationByCode.get(item.code);
      if (!station) return;
      var chip = el('button', 'recent-chip', station.name);
      chip.type = 'button';
      chip.addEventListener('click', function () { openStation(station); });
      recents.appendChild(chip);
    });
  }

  function stationRow(station) {
    var button = el('button', 'station-row');
    button.type = 'button';
    button.dataset.code = station.code;
    if (currentStation && currentStation.code === station.code) button.setAttribute('aria-current', 'true');
    button.setAttribute('aria-label', 'View departures at ' + station.name);
    var lineSet = el('span', 'station-badges' + (station.lines.length > 2 ? ' dense' : ''));
    station.lines.forEach(function (line) {
      var dot = badge(lineLetter(line.name), line.color);
      dot.title = line.name;
      lineSet.appendChild(dot);
    });
    var arrow = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    arrow.setAttribute('class', 'chevron');
    arrow.setAttribute('viewBox', '0 0 7 12');
    arrow.setAttribute('fill', 'none');
    arrow.setAttribute('stroke', 'currentColor');
    arrow.setAttribute('stroke-width', '1.1');
    arrow.setAttribute('aria-hidden', 'true');
    var path = document.createElementNS('http://www.w3.org/2000/svg', 'path');
    path.setAttribute('d', 'M.8 .8 6.2 6 .8 11.2');
    arrow.appendChild(path);
    button.append(lineSet, el('span', 'station-name', station.name), arrow);
    button.addEventListener('click', function () { openStation(station); });
    return button;
  }

  function renderStations() {
    var value = search.value.trim().toLocaleLowerCase('id-ID');
    listLabel.textContent = value ? 'SEARCH RESULTS' : 'ALL STATIONS';
    var shown = stations.filter(function (station) {
      return !value || station.name.toLocaleLowerCase('id-ID').includes(value) ||
        station.code.toLowerCase().includes(value);
    });
    results.replaceChildren();
    if (!shown.length) return empty(results, 'No stations found');
    var fragment = document.createDocumentFragment();
    shown.forEach(function (station) { fragment.appendChild(stationRow(station)); });
    results.appendChild(fragment);
  }

  function markSelectedStation() {
    results.querySelectorAll('.station-row').forEach(function (row) {
      if (currentStation && row.dataset.code === currentStation.code) row.setAttribute('aria-current', 'true');
      else row.removeAttribute('aria-current');
    });
  }

  async function loadStations() {
    try {
      var data = await getJSON('/api/stations?visibility=regular-v2');
      var byCode = new Map();
      (data.lines || []).forEach(function (line) {
        (line.stations || []).forEach(function (station) {
          if (!byCode.has(station.code)) {
            byCode.set(station.code, { code: station.code, name: station.name, lines: [] });
          }
          byCode.get(station.code).lines.push({ name: line.name, color: line.color });
        });
      });
      stationByCode = byCode;
      stations = Array.from(byCode.values()).sort(function (a, b) {
        return a.name.localeCompare(b.name, 'id');
      });
      renderRecents();
      renderStations();
      renderNetworkMap();
    } catch (error) {
      console.error('Station lookup failed:', error);
      empty(results, 'Unable to load stations');
    }
  }

  // ---------------------------------------------------------
  // BOARD STATE / API WIRING
  // ---------------------------------------------------------

  function openStation(station) {
    currentStation = station;
    currentLine = null;
    currentDirection = null;
    directionGroups = [];
    flatDepartures = [];
    cueByTrain = new Map();
    directionHistory = [];
    saveRecent(station);
    picker.hidden = !desktopMode.matches;
    board.hidden = false;
    idle.hidden = true;
    selectedTrain = undefined;
    markSelectedStation();
    $('name').textContent = station.name;
    // Preserves the prototype's line-colored left rail.
    board.style.borderLeftColor = station.lines[0] ? station.lines[0].color : '#dd3434';
    empty(list, 'Loading departures…');
    renderLineBadges();
    dirs.hidden = true;
    loadBoard();
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = setInterval(loadBoard, REFRESH_MS);
    window.scrollTo(0, 0);
  }

  function closeBoard() {
    requestVersion += 1;
    currentStation = null;
    currentLine = null;
    currentDirection = null;
    if (refreshTimer) clearInterval(refreshTimer);
    refreshTimer = null;
    board.hidden = true;
    picker.hidden = false;
    idle.hidden = !desktopMode.matches;
    selectedTrain = undefined;
    markSelectedStation();
    renderRecents();
    window.scrollTo(0, 0);
  }

  function renderLineBadges() {
    badges.replaceChildren();
    if (!currentStation) return;
    var multi = currentStation.lines.length > 1;
    currentStation.lines.forEach(function (line) {
      var letter = lineLetter(line.name);
      var b = el(multi ? 'button' : 'span', 'bd' + (currentLine && currentLine !== line.name ? ' dim' : ''), letter);
      b.style.backgroundColor = line.color;
      b.title = line.name;
      if (multi) {
        b.type = 'button';
        b.setAttribute('aria-label', 'Show ' + line.name + ' departures');
        b.setAttribute('aria-pressed', String(currentLine === line.name));
        b.addEventListener('click', function () {
          currentLine = currentLine === line.name ? null : line.name;
          currentDirection = null;
          renderLineBadges();
          renderDirectionChips();
          loadBoard();
        });
      }
      badges.appendChild(b);
    });
  }

  function normalizedVia(value) {
    var via = String(value || '');
    var station = stationByCode.get(via.toUpperCase());
    return station ? station.name : via;
  }

  function directionEnded(direction) {
    return !direction.arrivals.some(function (train) {
      return minutesAway(train.arrival_time) >= 0;
    }) && direction.last_departure &&
      direction.last_sort < serviceSortNow();
  }

  function renderDirectionChips() {
    var show = currentStation && FORK_STATIONS.has(currentStation.code) &&
      directionGroups.length > 0;
    dirs.hidden = !show;
    if (!show) currentDirection = null;
    clearButton.hidden = !currentDirection && !currentLine;
    grid.replaceChildren();
    if (!show) return;

    directionGroups.forEach(function (direction, index) {
      var on = currentDirection === direction.key;
      var chip = el('button', 'chip' + (on ? ' on' : '') +
        (directionGroups.length % 2 === 1 && index === directionGroups.length - 1 ? ' wide' : ''));
      chip.type = 'button';
      chip.setAttribute('aria-pressed', String(on));
      chip.setAttribute('aria-label', 'Show trains toward ' + direction.label +
        (direction.via ? ' via ' + direction.via : ''));
      if (on) chip.style.backgroundColor = direction.color;

      var symbol = badge(lineLetter(direction.line), on ? '#fff' : direction.color);
      if (on) symbol.style.color = direction.color;
      var title = el('span');
      title.appendChild(el('span', 'cn', direction.label));
      if (directionEnded(direction)) {
        title.appendChild(el('span', 'cv', 'no more today'));
      } else if (direction.via) {
        title.appendChild(el('span', 'cv', 'via ' + direction.via));
      }
      chip.append(symbol, title);
      chip.addEventListener('click', function () {
        currentDirection = currentDirection === direction.key ? null : direction.key;
        currentLine = null;
        // Cancel an in-flight refresh before changing the board view.
        requestVersion++;
        renderLineBadges();
        renderDirectionChips();
        paintDepartures();
      });
      grid.appendChild(chip);
    });
  }

  async function loadBoard() {
    if (!currentStation) return;
    var stationCode = currentStation.code;
    var requestedLine = currentLine;
    var version = ++requestVersion;
    var baseURL = '/api/stations/' + encodeURIComponent(stationCode);
    var url = baseURL + '/arrivals';
    if (requestedLine) url += '?line=' + encodeURIComponent(requestedLine);

    try {
      // Cues are supplementary. If the endpoint is unavailable, the normal
      // board stays usable, but no "last train" claims are made.
      var pair = await Promise.all([
        getJSON(url),
        getJSON(baseURL + '/cues').catch(function (error) {
          console.warn('Schedule cues unavailable:', error); return null;
        })
      ]);
      if (version !== requestVersion || !currentStation ||
          currentStation.code !== stationCode || currentLine !== requestedLine) return;

      flatDepartures = pair[0].arrivals || [];
      cueByTrain = new Map();
      directionHistory = [];
      if (pair[1]) {
        (pair[1].cues || []).forEach(function (cue) {
          cueByTrain.set(cueKey(cue.train_id, cue.departure_time), cue);
        });
        directionHistory = pair[1].directions || [];
        directionGroups = FORK_STATIONS.has(stationCode) ? (pair[1].forks || []) : [];
        if (currentDirection && !directionGroups.some(function (d) {
          return d.key === currentDirection;
        })) currentDirection = null;
      } else {
        // Never infer "forks" from the next few destinations. When the
        // optional cue endpoint is unavailable, retain the plain board.
        directionGroups = [];
        currentDirection = null;
      }

      renderDirectionChips();
      paintDepartures();
    } catch (error) {
      if (version !== requestVersion || !currentStation) return;
      console.error('Departures unavailable:', error);
      empty(list, 'Unable to load departures');
    }
  }

  // The network schematic is a navigation aid, not a geographical map.
  var MAP = {"nodes":{"TNG":[30,44,-4,-14,"start"],"DU":[92,120,-12,4,"end"],"KPB":[215,72,-7,-16,"end"],"JAKK":[160,128,12,4,"start"],"TPK":[350,36,0,-14,"middle"],"PSE":[330,128,12,4,"start"],"THB":[92,215,-12,4,"end"],"MRI":[215,215,-10,22,"end"],"JNG":[330,215,0,22,"middle"],"CKR":[400,215,10,-14,"end"],"RK":[40,380,12,4,"start"],"CTA":[215,330,12,4,"start"],"BOO":[170,410,0,18,"middle"],"NMO":[280,410,0,18,"middle"]},"edges":[["KPB","TPK","#DD0067"],["KPB","JAKK","#DD0067"],["JAKK","MRI","#E30A16"],["MRI","CTA","#E30A16"],["CTA","BOO","#E30A16"],["CTA","NMO","#E30A16"],["KPB","DU","#0084D8"],["DU","THB","#0084D8"],["THB","MRI","#0084D8"],["MRI","JNG","#0084D8"],["JNG","CKR","#0084D8"],["KPB","PSE","#0084D8"],["PSE","JNG","#0084D8"],["DU","TNG","#623814"],["THB","RK","#16812B"]],"forks":["MRI","KPB","JNG","CTA","DU","THB"]};


  function renderNetworkMap() {
    var box = $('map');
    if (!box) return;
    box.replaceChildren();
    var ns = 'http://www.w3.org/2000/svg';
    var svg = document.createElementNS(ns, 'svg');
    svg.setAttribute('viewBox', '0 0 430 440');
    svg.setAttribute('role', 'group');
    svg.setAttribute('aria-label', 'Kommute network schematic');
    function mk(tag, attrs) {
      var e = document.createElementNS(ns, tag);
      Object.keys(attrs).forEach(function (k) { e.setAttribute(k, attrs[k]); });
      return e;
    }
    MAP.edges.forEach(function (edge) {
      var a = MAP.nodes[edge[0]], b = MAP.nodes[edge[1]];
      svg.appendChild(mk('line', {x1:a[0], y1:a[1], x2:b[0], y2:b[1],
        stroke:edge[2], 'stroke-width':5, 'stroke-linecap':'round'}));
    });
    Object.keys(MAP.nodes).forEach(function (code) {
      var station = stationByCode.get(code);
      if (!station) return;
      var n = MAP.nodes[code];
      var fork = MAP.forks.includes(code);
      var group = mk('g', {'class':'n', tabindex:0, role:'button',
        'aria-label':'Open '+station.name});
      if (fork) group.appendChild(mk('circle', {
        cx:n[0], cy:n[1], r:11, fill:'#fff', stroke:'#11110f', 'stroke-width':1}));
      group.appendChild(mk('circle', {
        cx:n[0], cy:n[1], r:fork?6.5:5, fill:'#fff',
        stroke:'#11110f', 'stroke-width':fork?3:2.5}));
      var label = mk('text', {x:n[0]+n[2], y:n[1]+n[3], 'text-anchor':n[4]});
      label.textContent = station.name;
      group.appendChild(label);
      group.addEventListener('click', function () { openStation(station); });
      group.addEventListener('keydown', function (event) {
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault(); openStation(station);
        }
      });
      svg.appendChild(group);
    });
    box.appendChild(svg);
  }

  function trainKey(train) { return String(train.train_id) + '|' + train.arrival_time; }

  function getRoute(train) {
    var station = currentStation.code;
    var key = station + '|' + train.train_id;
    if (!routeCache.has(key)) {
      var url = '/api/stations/' + encodeURIComponent(station) +
        '/trains/' + encodeURIComponent(train.train_id) + '/route';
      var promise = getJSON(url).then(function (data) { return data.stops || []; })
        .catch(function (error) {
          routeCache.delete(key);
          throw error;
        });
      routeCache.set(key, promise);
    }
    return routeCache.get(key);
  }

  function otherLines(code, currentLine) {
    var station = stationByCode.get(code);
    if (!station) return [];
    return station.lines.filter(function (line) { return line.name !== currentLine; }).slice(0, 2);
  }

  function buildStrip(stops, line, color) {
    var content = el('div', 'strip');
    if (!stops.length) return content;
    var after = stops.slice(1);
    var nodes = [{stop:stops[0], here:true}];
    if (after.length <= 6) {
      after.forEach(function (stop, i) {
        nodes.push({stop:stop, end:i === after.length - 1});
      });
    } else {
      after.slice(0, 4).forEach(function (stop) { nodes.push({stop:stop}); });
      nodes.push({gap:after.length - 5});
      nodes.push({stop:after[after.length-1], end:true});
    }
    content.style.gridTemplateColumns = 'repeat(' + nodes.length + ',1fr)';
    content.style.width = (nodes.length / 7 * 100) + '%';
    content.style.setProperty('--c', color);
    nodes.forEach(function (entry, index) {
      var cell = el('div', 'nd' + (entry.here?' here key':'') +
        (entry.end?' key':'') + (entry.gap?' gap':''));
      var prevGap = index > 0 && !!nodes[index-1].gap;
      var nextGap = index < nodes.length-1 && !!nodes[index+1].gap;
      if (index > 0) cell.appendChild(el('i', 'ln l' + (entry.gap || prevGap ? ' dash' : '')));
      if (index < nodes.length-1) cell.appendChild(el('i', 'ln r' + (entry.gap || nextGap ? ' dash' : '')));
      if (entry.gap) {
        cell.appendChild(el('span', 'nm', '+' + entry.gap + ' stops'));
      } else {
        cell.appendChild(el('i', 'dot'));
        if (!entry.here) otherLines(entry.stop.code, line).forEach(function (other, idx) {
          var transfer = el('i', 'xf', lineLetter(other.name));
          transfer.style.left = 'calc(50% + ' + (idx * 15 - 7) + 'px)';
          transfer.style.backgroundColor = other.color;
          transfer.title = other.name;
          cell.appendChild(transfer);
        });
        cell.appendChild(el('span', 'nm', entry.stop.name));
        cell.appendChild(el('span', 'tm', entry.stop.time));
      }
      content.appendChild(cell);
    });
    return content;
  }

  function buildExpandedStops(stops, line, color) {
    var section = el('div', 'xp');
    section.appendChild(el('h4', '', 'STOPS AFTER ' + currentStation.name));
    var items = el('ol', 'xl');
    stops.slice(1).forEach(function (stop, idx, arr) {
      var final = idx === arr.length-1;
      var item = el('li', final ? 'end' : '');
      item.style.setProperty('--c', color);
      item.append(el('span','d'), el('span','n',stop.name));
      otherLines(stop.code, line).forEach(function (other) {
        var b=el('i','xb',lineLetter(other.name));
        b.style.backgroundColor=other.color;
        b.title=other.name;
        item.appendChild(b);
      });
      if (final) item.appendChild(el('span','tg','ENDS HERE'));
      item.appendChild(el('span','t',stop.time));
      items.appendChild(item);
    });
    section.appendChild(items);
    return section;
  }

  function paintDepartures() {
    var departures;
    var direction = null;
    if (currentDirection) {
      direction = directionGroups.find(function (item) { return item.key === currentDirection; });
      departures = direction ? direction.arrivals.filter(function (train) {
        return minutesAway(train.arrival_time) >= 0;
      }).slice(0, MAX_ROWS) : [];
    } else {
      departures = flatDepartures.filter(function (train) {
        return minutesAway(train.arrival_time) >= 0 &&
          (!currentLine || train.line === currentLine);
      }).slice(0, MAX_ROWS);
    }

    list.replaceChildren();
    if (!departures.length) {
      if (direction && directionEnded(direction)) {
        var message = el('div', 'none', 'No more trains toward ' + direction.label + ' today');
        message.appendChild(el('span', '', 'The last one left at ' + direction.last_departure.slice(0, 5)));
        list.appendChild(message);
      } else if (!currentDirection && directionHistory.length > 0 &&
        directionHistory.every(function (history) { return history.last_sort < serviceSortNow(); })) {
        empty(list, 'No more scheduled departures today');
      } else {
        empty(list, 'No upcoming departures');
      }
      return;
    }

    if (desktopMode.matches && (selectedTrain === undefined ||
      (selectedTrain !== null && !departures.some(function (t) { return trainKey(t) === selectedTrain; })))) {
      selectedTrain = trainKey(departures[0]);
    }

    var visibleTrains = new Set(departures.map(function (train) {
      return cueKey(train.train_id, train.arrival_time);
    }));

    var fragment = document.createDocumentFragment();
    departures.forEach(function (train) {
      var key = trainKey(train);
      var open = desktopMode.matches && selectedTrain === key;
      var item = el('div', 'item' + (open ? ' open' : ''));
      var row = el('div', 'row');
      row.dataset.departure = train.arrival_time;
      var left = el('div', 'l');
      var symbol = badge(lineLetter(train.line), train.color);
      var destination = el('span', 'dest', train.destination);
      if (train.via) destination.appendChild(el('small', '', 'via ' + normalizedVia(train.via)));

      var cue = cueByTrain.get(cueKey(train.train_id, train.arrival_time));
      if (cue) {
        if (cue.last_train) {
          var lastBadge = el('span', 'pill last', 'LAST TRAIN');
          lastBadge.title = 'Last scheduled direct train reaching ' + train.destination + ' this service day';
          destination.appendChild(lastBadge);
        } else if (cue.next_time &&
          !visibleTrains.has(cueKey(cue.next_train_id, cue.next_time))) {
          var nextBadge = el('span', 'pill next', 'NEXT ' + cue.next_time.slice(0, 5));
          nextBadge.title = 'Next scheduled direct train reaching ' + train.destination;
          destination.appendChild(nextBadge);
        }
      }
      left.append(symbol, destination);

      var middle = el('div', 'mid');
      var right = el('div', 'r');
      var label = etaLabel(train.arrival_time);
      right.append(el('div', 'cd' + (label === 'NOW' ? ' now' : ''), label),
        el('div', 'ck', train.arrival_time.slice(0, 5)));
      row.append(left, middle, right);
      row.setAttribute('role', 'button');
      row.tabIndex = desktopMode.matches ? 0 : -1;
      row.setAttribute('aria-expanded', String(open));
      row.addEventListener('click', function () {
        if (!desktopMode.matches) return;
        selectedTrain = selectedTrain === key ? null : key;
        paintDepartures();
      });
      row.addEventListener('keydown', function (event) {
        if (!desktopMode.matches) return;
        if (event.key === 'Enter' || event.key === ' ') {
          event.preventDefault();
          selectedTrain = selectedTrain === key ? null : key;
          paintDepartures();
        }
      });
      item.appendChild(row);
      fragment.appendChild(item);

      if (desktopMode.matches) {
        // Fetch only train routes that are actually on the desktop board.
        // Results are cached and reused on refresh or row selection.
        getRoute(train).then(function (stops) {
          if (!item.isConnected || !currentStation ||
            row.closest('#list') !== list) return;
          middle.replaceChildren(buildStrip(stops, train.line, train.color));
          if (open) item.appendChild(buildExpandedStops(stops, train.line, train.color));
        }).catch(function (error) {
          if (!item.isConnected) return;
          var fallback = el('span', 'route-unavailable', 'Route details unavailable');
          middle.replaceChildren(fallback);
          if (open) item.appendChild(el('div', 'empty', 'Unable to load train stops'));
        });
      }
    });
    list.appendChild(fragment);
    document.title = currentStation.name + ' — Kommute';
  }

  function updateETAs() {
    showClock();
    if (!currentStation) return;

    // Remove expired services immediately; don't leave 'NOW' showing for
    // multiple minutes while waiting for the 60-second API refresh.
    var expired = Array.from(list.querySelectorAll('.row')).some(function (row) {
      return minutesAway(row.dataset.departure) < 0;
    });
    if (expired) {
      renderDirectionChips();
      paintDepartures();
      loadBoard(); // Replenish the board from the next valid services.
      return;
    }

    list.querySelectorAll('.row').forEach(function (row) {
      var text = etaLabel(row.dataset.departure);
      var node = row.querySelector('.cd');
      node.className = 'cd' + (text === 'NOW' ? ' now' : '');
      node.textContent = text;
    });
  }

  $('back').addEventListener('click', closeBoard);
  $('home').addEventListener('click', closeBoard);
  desktopMode.addEventListener('change', function () {
    picker.hidden = !!currentStation && !desktopMode.matches;
    idle.hidden = !!currentStation || !desktopMode.matches;
    selectedTrain = undefined;
    if (currentStation) paintDepartures();
  });
  clearButton.addEventListener('click', function () {
    currentDirection = null;
    currentLine = null;
    renderLineBadges();
    renderDirectionChips();
    loadBoard();
  });
  search.addEventListener('input', renderStations);
  showClock();
  idle.hidden = !desktopMode.matches;
  empty(results, 'Loading stations…');
  loadStations();
  setInterval(updateETAs, CLOCK_MS);
})();
