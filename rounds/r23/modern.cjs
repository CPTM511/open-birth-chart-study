/* SPDX-License-Identifier: AGPL-3.0-or-later */
'use strict';
const fs = require('node:fs');
const path = require('node:path');
const bridge = require('../../src/open_birth_chart/ziwei_bridge.cjs');
const fromInstall = name => process.env.OBS_NODE_MODULES
  ? require(path.join(process.env.OBS_NODE_MODULES, name)) : require(name);
const iztro = fromInstall('iztro');
const calendar = fromInstall('lunar-lite');
const STEMS = '甲乙丙丁戊己庚辛壬癸';
const BRANCHES = '子丑寅卯辰巳午未申酉戌亥';
const BUREAUS = {'水二局': 2, '木三局': 3, '金四局': 4, '土五局': 5, '火六局': 6};
const PERIOD_BASES = [1924, 1984];
const cycle = Array.from({length: 60}, (_, i) => STEMS[i % 10] + BRANCHES[i % 12]);

function lunarInputs(date) {
  const {lunarYear, lunarMonth, lunarDay, isLeap} = date;
  return {year: lunarYear, month: lunarMonth, day: lunarDay, is_leap: isLeap};
}

function extract(life, body, bureauName, palaces) {
  const stars = {};
  for (const [branch, names] of palaces) {
    for (const star of names) {
      if (Object.hasOwn(stars, star)) throw new Error('Duplicate computed major star: ' + star);
      stars[star] = [branch];
    }
  }
  const bureau = BUREAUS[bureauName];
  if (!BRANCHES.includes(life) || !BRANCHES.includes(body)
      || !bureau || palaces.length !== 12 || Object.keys(stars).length !== 14) {
    throw new Error('Incomplete Iztro natal chart');
  }
  return {life, body, bureau, stars};
}

function assertSamePlacement(direct, fromBridge, slot) {
  for (const key of ['life', 'body', 'bureau']) {
    if (direct[key] !== fromBridge[key]) throw new Error(slot + ': direct and bridge disagree on ' + key);
  }
  for (const [star, location] of Object.entries(direct.stars)) {
    if (location[0] !== fromBridge.stars[star]?.[0]) {
      throw new Error(slot + ': direct and bridge disagree on ' + star);
    }
  }
}

function evaluate(caseInput) {
  const {slot, birth} = caseInput;
  const cycleIndex = cycle.indexOf(birth.ganzhi);
  const hourIndex = BRANCHES.indexOf(birth.hour_branch);
  if (cycleIndex < 0 || hourIndex < 0) throw new Error(slot + ': invalid year or hour branch');
  const branches = hourIndex === 0 ? [['early_zi', 0], ['late_zi', 12]] : [['fixed', hourIndex]];
  const attempts = [];
  for (const base of PERIOD_BASES) {
    const year = base + cycleIndex;
    const lunarDate = [year, birth.lunar_month, birth.lunar_day].join('-');
    let solar;
    let originalLunar;
    let originalYear;
    try {
      const converted = calendar.lunar2solar(lunarDate, birth.is_leap);
      solar = [String(converted.solarYear), converted.solarMonth, converted.solarDay]
        .map(s => String(s).padStart(2, '0')).join('-');
      originalLunar = lunarInputs(calendar.solar2lunar(solar));
      originalYear = calendar.getHeavenlyStemAndEarthlyBranchBySolarDate(solar, 0, {
        year: bridge.CONFIG.yearDivide, month: bridge.CONFIG.horoscopeDivide,
      }).yearly.join('');
    } catch (error) {
      attempts.push({year, status: 'invalid_calendar_carrier', reason: error.message});
      continue;
    }
    if (originalYear !== birth.ganzhi || originalLunar.year !== year
        || originalLunar.month !== birth.lunar_month || originalLunar.day !== birth.lunar_day
        || originalLunar.is_leap !== birth.is_leap) {
      attempts.push({year, solar_date: solar, status: 'failed_calendar_roundtrip', readback: originalLunar});
      continue;
    }
    if (!['M', 'F'].includes(birth.sex)) {
      attempts.push({year, solar_date: solar, status: 'missing_sex'});
      continue;
    }
    const variants = [];
    for (const [branch, timeIndex] of branches) {
      const chart = iztro.astro.withOptions({
        type: 'lunar', dateStr: lunarDate, timeIndex, gender: birth.sex === 'M' ? '男' : '女',
        isLeapMonth: birth.is_leap, fixLeap: true, config: bridge.CONFIG,
      });
      const placements = extract(chart.earthlyBranchOfSoulPalace, chart.earthlyBranchOfBodyPalace,
        chart.fiveElementsClass, chart.palaces.map(p => [p.earthlyBranch, p.majorStars.map(s => s.name)]));
      const processedLunar = lunarInputs(chart.rawDates.lunarDate);
      const hour = timeIndex === 12 ? 23 : timeIndex * 2;
      const clock = String(hour).padStart(2, '0') + ':00';
      const solarYear = Number(solar.slice(0, 4));
      let bridgeStatus = 'outside_r8_solar_year_scope';
      if (solarYear >= 1880 && solarYear <= 2019) {
        const replay = bridge.evaluate({
          row: {birth_local: solar + 'T' + clock, sex: birth.sex}, include_chart: true,
        });
        if (!replay.chart || replay.time_index !== timeIndex) {
          throw new Error(slot + ': R8 bridge failed: ' + replay.reason);
        }
        const c = replay.chart;
        const baseline = extract(c.soul_branch, c.body_branch, c.five_elements_class,
          c.palaces.map(p => [p.earthly_branch, p.major_stars.map(s => s.name)]));
        assertSamePlacement(placements, baseline, slot);
        for (const [field, value] of Object.entries(processedLunar)) {
          if (lunarInputs(c.raw_lunar_date)[field] !== value) {
            throw new Error(slot + ': direct and bridge disagree on the processed lunar day');
          }
        }
        bridgeStatus = 'equal';
      }
      variants.push({branch, time_index: timeIndex, interface_clock: clock,
        processed_lunar_date: processedLunar, r8_bridge: bridgeStatus, ...placements});
    }
    attempts.push({year, solar_date: solar, status: 'valid', roundtrip_lunar_date: originalLunar,
      roundtrip_ganzhi: originalYear, variants});
  }
  return {slot, attempts};
}

const charts = JSON.parse(fs.readFileSync(0, 'utf8'));
process.stdout.write(JSON.stringify(charts.map(evaluate)) + '\n');
