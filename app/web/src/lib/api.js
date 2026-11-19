// FastAPI(app/api) 호출. Next.js가 /api/*를 API 서버로 넘긴다(next.config.mjs).

export class ApiError extends Error {}

export class ApiClient {
  constructor(base = "/api") {
    this.base = base;
  }

  async get(path, params) {
    const query = params ? `?${new URLSearchParams(params)}` : "";
    let response;
    try {
      response = await fetch(`${this.base}${path}${query}`, { cache: "no-store" });
    } catch {
      throw new ApiError("API 서버에 연결할 수 없습니다");
    }
    if (!response.ok) throw new ApiError(`API 오류 ${response.status}: ${path}`);
    return response.json();
  }

  meta() {
    return this.get("/meta");
  }

  summary() {
    return this.get("/summary");
  }

  /** 시나리오 하나의 전체 데이터: meta·limits, 모든 shot, 알람. */
  async scenario(id) {
    const [head, shots, alarms] = await Promise.all([
      this.get(`/scenarios/${id}`),
      this.get(`/scenarios/${id}/shots`, { offset: 0, limit: 2000 }),
      this.get(`/scenarios/${id}/alarms`),
    ]);
    return { ...head, shots: shots.shots, alarms };
  }
}
