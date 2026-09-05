"use client";
import { useEffect, useState } from "react";
import RolePicker from "@/components/RolePicker";
import { api, fallback, type Role } from "@/lib/api";
export default function RolesPage() {
  const [roles, setRoles] = useState<Role[]>(fallback.roles);
  const [preview, setPreview] = useState(false);
  useEffect(() => {
    api
      .roles()
      .then((r) => setRoles(r.roles))
      .catch(() => setPreview(true));
  }, []);
  return (
    <section className="section">
      <div className="shell">
        <div
          style={{
            display: "flex",
            justifyContent: "space-between",
            alignItems: "center",
          }}
        >
          <div>
            <div className="kicker">Choose a role</div>
            <h1
              className="display serif"
              style={{ fontSize: "clamp(42px,6vw,64px)" }}
            >
              Where do you want to aim?
            </h1>
          </div>
          {preview && <span className="preview">API fallback active</span>}
        </div>
        <p
          className="quiet"
          style={{ maxWidth: 640, fontSize: 18, marginBottom: 54 }}
        >
          Compare what you already know with the skills employers request.
          Posting counts show how much evidence sits behind each profile.
        </p>
        <RolePicker roles={roles} />
      </div>
    </section>
  );
}
