export const API_URL =
  process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

export type Trend = {
  rank_slope: number;
  direction: "rising" | "falling" | "flat";
  years_observed: number;
  latest_adoption?: number;
  desire_gap?: number;
  rank_series?: Record<string, number>;
  series?: Record<string, number>;
  source?: string;
  caveat?: string;
};
export type SkillRef = {
  skill: string;
  support: number;
  lift: number;
  by_seniority?: Record<string, number>;
  trend?: Trend | null;
};
export type Role = {
  name: string;
  postings: number;
  by_seniority: Record<string, number>;
  distinct_skills: number;
};
export type Recommendation = {
  rank: number;
  skill: string;
  score: number;
  category: string;
  postings_mentioning: number;
  role_support?: number | null;
  trend?: Trend | null;
};
export type RoleMatch = {
  role: string;
  coverage: number;
  matched_skills: string[];
  top_missing: string[];
  postings: number;
};

const FALLBACK_ROLES: Role[] = [
  {
    name: "Software Engineer",
    postings: 13795,
    by_seniority: {
      junior: 684,
      mid: 7241,
      senior: 4380,
      staff: 342,
      lead: 891,
      principal: 257,
    },
    distinct_skills: 284,
  },
  {
    name: "Data Engineer",
    postings: 1330,
    by_seniority: {
      junior: 42,
      mid: 582,
      senior: 501,
      staff: 35,
      lead: 139,
      principal: 31,
    },
    distinct_skills: 118,
  },
  {
    name: "AI/ML Engineer",
    postings: 1502,
    by_seniority: {
      junior: 89,
      mid: 741,
      senior: 491,
      staff: 29,
      lead: 126,
      principal: 26,
    },
    distinct_skills: 142,
  },
  {
    name: "Developer, Front-end",
    postings: 593,
    by_seniority: {
      junior: 48,
      mid: 302,
      senior: 183,
      staff: 11,
      lead: 42,
      principal: 7,
    },
    distinct_skills: 91,
  },
  {
    name: "DevOps Engineer",
    postings: 789,
    by_seniority: {
      junior: 31,
      mid: 381,
      senior: 271,
      staff: 22,
      lead: 68,
      principal: 16,
    },
    distinct_skills: 126,
  },
  {
    name: "Security Professional",
    postings: 776,
    by_seniority: {
      junior: 38,
      mid: 337,
      senior: 273,
      staff: 21,
      lead: 82,
      principal: 25,
    },
    distinct_skills: 103,
  },
];
const FALLBACK_SKILLS = [
  "Python",
  "JavaScript",
  "TypeScript",
  "React",
  "Node.js",
  "SQL",
  "Docker",
  "Kubernetes",
  "AWS",
  "Git",
  "Terraform",
  "Apache Spark",
  "Airflow",
  "Data Modeling",
  "Go",
  "Rust",
  "GraphQL",
  "PostgreSQL",
];

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers:
      init?.body instanceof FormData
        ? init.headers
        : { "Content-Type": "application/json", ...init?.headers },
  });
  if (!response.ok)
    throw new Error(
      (await response.text()) || `Request failed (${response.status})`,
    );
  return response.json() as Promise<T>;
}

export const api = {
  health: () =>
    request<{
      ready: boolean;
      errors: string[];
      skills: number;
      roles: number;
      trends: number;
    }>("/health"),
  normalize: (skills: string[]) =>
    request<
      Array<{
        input: string;
        canonical: string | null;
        category: string | null;
      }>
    >("/skills/normalize", {
      method: "POST",
      body: JSON.stringify({ skills }),
    }),
  recommend: (skills: string[], target_role?: string) =>
    request<{
      method: string;
      recognised: string[];
      unrecognised: string[];
      target_role?: string;
      recommendations: Recommendation[];
      note: string;
    }>("/recommend/skills", {
      method: "POST",
      body: JSON.stringify({
        skills,
        top_k: 10,
        target_role,
        method: "hybrid",
      }),
    }),
  vocabulary: () =>
    request<{
      skills: Array<{
        canonical: string;
        category: string | null;
        postings_mentioning: number | null;
      }>;
    }>("/skills"),
  roles: () => request<{ roles: Role[] }>("/roles"),
  gap: (skills: string[], role: string) =>
    request<{
      role: string;
      postings_analysed: number;
      coverage: number;
      you_have: SkillRef[];
      gaps: SkillRef[];
      note: string;
    }>("/roles/gap", {
      method: "POST",
      body: JSON.stringify({ skills, role, top_k: 15 }),
    }),
  match: (skills: string[]) =>
    request<{ recognised: string[]; roles: RoleMatch[] }>("/roles/match", {
      method: "POST",
      body: JSON.stringify({ skills }),
    }),
  skill: (name: string) =>
    request<{
      canonical: string;
      category: string;
      in_survey: boolean;
      postings_mentioning: number;
      degree: number;
      trend?: Trend | null;
      co_occurring_distinctive: Array<{
        skill: string;
        pmi: number;
        postings: number;
      }>;
      co_occurring_frequent: Array<{
        skill: string;
        pmi: number;
        postings: number;
      }>;
      roles_requiring: Array<{ role: string; support: number; lift: number }>;
    }>(`/skills/${encodeURIComponent(name)}`),
  trends: (direction: "rising" | "falling") =>
    request<{
      direction: string;
      skills: Array<{
        skill: string;
        rank_slope: number;
        latest_adoption: number;
        years_observed: number;
        desire_gap?: number;
      }>;
      note: string;
    }>(`/trends?direction=${direction}&limit=20`),
  trend: (name: string) =>
    request<Trend & { skill: string }>(`/trends/${encodeURIComponent(name)}`),
  resume: (file: File) => {
    const body = new FormData();
    body.append("file", file);
    return request<{
      sections_found: Record<string, number>;
      skills: Array<{
        skill: string;
        weight: number;
        section: string;
        matched_text: string;
        elementary: boolean;
        trend?: Trend | null;
      }>;
      unmatched_terms: string[];
      recommendations: Recommendation[];
      role_match: RoleMatch[];
    }>("/resume/analyze", { method: "POST", body });
  },
};

/* FALLBACK DATA: development-only previews while the backend is unavailable.
   Every use is labelled in the UI. Remove this object before production. */
export const fallback = {
  health: {
    ready: false,
    errors: ["Backend unavailable — showing a local preview"],
    skills: 3250,
    roles: 21,
    trends: 457,
  },
  roles: FALLBACK_ROLES,
  vocabulary: FALLBACK_SKILLS,
  recommendations(skills: string[]): Recommendation[] {
    return FALLBACK_SKILLS.filter(
      (s) => !skills.some((x) => x.toLowerCase() === s.toLowerCase()),
    )
      .slice(0, 8)
      .map((skill, i) => ({
        rank: i + 1,
        skill,
        score: 8 - i,
        category: i < 5 ? "Tool" : "Language",
        postings_mentioning: [5367, 5049, 4321, 3802, 2950, 2418, 1984, 1738][
          i
        ],
        trend:
          i === 1
            ? {
                rank_slope: 0.052,
                direction: "rising",
                years_observed: 6,
                latest_adoption: 0.285,
              }
            : null,
      }));
  },
  gap(skills: string[], role: string) {
    const pool = [
      "Python",
      "SQL",
      "Docker",
      "Apache Spark",
      "Data Modeling",
      "Airflow",
      "AWS",
      "Kubernetes",
    ];
    const rows: SkillRef[] = pool.map((skill, i) => ({
      skill,
      support: 0.69 - i * 0.055,
      lift: 0.91 + i * 0.19,
      by_seniority: {
        junior: 0.52 - i * 0.04,
        mid: 0.61 - i * 0.045,
        senior: 0.69 - i * 0.05,
        lead: 0.72 - i * 0.05,
      },
      trend:
        i === 3 || i === 5
          ? { rank_slope: 0.04, direction: "rising", years_observed: 6 }
          : null,
    }));
    const has = rows.filter((r) =>
      skills.some((s) => s.toLowerCase() === r.skill.toLowerCase()),
    );
    return {
      role,
      postings_analysed:
        FALLBACK_ROLES.find((r) => r.name === role)?.postings ?? 1072,
      coverage: Math.min(0.78, has.length * 0.11),
      you_have: has,
      gaps: rows.filter((r) => !has.includes(r)),
      note: "Preview data illustrates the API response shape; connect the backend for measured results.",
    };
  },
};
