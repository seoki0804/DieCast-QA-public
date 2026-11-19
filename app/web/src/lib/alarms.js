// 알람 센터: 백엔드가 미리 계산한 경고·정보·기록 알람과, 화면에서 만드는 '주의'(위험도 상 제품)를
// 재생 위치에 맞춰 보여 준다 (9단계 OCAP, DESIGN_SYSTEM.md 6장).

export const LEVELS = ["critical", "warning", "info", "log"];

export class AlarmCenter {
  /**
   * @param {object[]} alarms 백엔드 알람 (at: 반영 위치, release_at: 해제 위치 또는 null)
   * @param {{warningWindow?: number}} options 주의 알람을 묶는 shot 수 (토스트는 이 간격당 1개)
   */
  constructor(alarms, { warningWindow = 10 } = {}) {
    this.alarms = [...alarms].sort((a, b) => a.at - b.at || a.level_rank - b.level_rank);
    this.warningWindow = warningWindow;
  }

  /** 알람의 현재 상태: active(진행 중) · resolved(해제) · logged(기록). */
  status(alarm, position) {
    if (alarm.level === "log") return "logged";
    if (alarm.level === "warning") return "active";
    if (alarm.release_at != null && position >= alarm.release_at) return "resolved";
    return "active";
  }

  /** 재생 위치까지 발생한 알람 (최근 순). */
  history(position) {
    const out = [];
    for (const alarm of this.alarms) {
      if (alarm.at > position) break;
      out.push(alarm);
    }
    return out.reverse();
  }

  /** 진행 중인 경고·정보 알람. */
  active(position) {
    return this.history(position).filter(
      (a) => (a.level === "critical" || a.level === "info") && this.status(a, position) === "active",
    );
  }

  /**
   * '주의' 알람: warningWindow shot마다 위험도 상 제품을 한 알람으로 묶는다 (알람 피로 방지).
   * 아직 끝나지 않은 묶음도 지금까지의 제품으로 보여 준다. 전수검사 모드인 shot과 경고 뒤 전수검사
   * 구간은 모든 제품을 검사하므로 제품별로 알리지 않는다.
   */
  warnings(shots, position, ledger) {
    const out = [];
    for (let start = 0; start <= position; start += this.warningWindow) {
      const end = Math.min(start + this.warningWindow - 1, position);
      const flagged = [];
      for (let i = start; i <= end; i += 1) {
        if (shots[i].tight || ledger.inspectsAll(i)) continue;
        for (const part of shots[i].parts) {
          if (ledger.risk(part, shots[i]) === "high") flagged.push({ index: i, shot: shots[i], part });
        }
      }
      if (!flagged.length) continue;
      const at = flagged[0].index;
      out.push({
        id: `warning-${start}`,
        level: "warning",
        level_rank: 1,
        rule: "high_risk",
        at,
        detected_at: at,
        title: `위험도 상 제품 ${flagged.length}건`,
        message: `shot ${shots[start].shot}~${shots[end].shot} · 검사 기준 ${(ledger.thresholdAt(start) * 100).toFixed(1)}% 이상`,
        release_at: null,
        parts: flagged,
      });
    }
    return out.reverse();
  }

  /** 100 shot당 알람 수 (주의 제외: 경고·정보·기록). */
  ratePer100(position) {
    const n = this.history(position).length;
    return position >= 0 ? (n / (position + 1)) * 100 : 0;
  }

  countByLevel(position) {
    const counts = Object.fromEntries(LEVELS.map((l) => [l, 0]));
    for (const alarm of this.history(position)) counts[alarm.level] += 1;
    return counts;
  }
}
