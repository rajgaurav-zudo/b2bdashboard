import { Fragment, useState } from "react";
import type { FormEvent } from "react";

import { useModules, useUserChange, useUsers } from "../api/client";
import type { ModuleInfo, UserRow } from "../api/types";
import { SIGN_IN_DOMAIN, authRequired, useAuth } from "../auth";
import type { Role } from "../auth";
import { when } from "../format";
import { Band, Empty, Section, Spinner } from "../ui/Primitives";

const ROLE_LABEL: Record<Role, string> = { owner: "Owner", admin: "Admin", member: "Member" };

/** Who may sign in. Being in the Google Workspace is not enough on its own:
 *  someone has to be added here first.
 *
 *  The page offers only what the API would allow -- the owner manages everyone,
 *  an admin manages members -- but the API is what enforces it. */
export function UsersPage() {
  const { email: me, role, isAdmin } = useAuth();
  const list = useUsers(authRequired && isAdmin);
  const modules = useModules(authRequired && isAdmin);
  const change = useUserChange();
  const [editing, setEditing] = useState<string | null>(null);

  const header = (
    <header className="top">
      <div className="top-in">
        <h1>Users</h1>
        <p className="sub">
          Only the people listed here can sign in, with their @{SIGN_IN_DOMAIN} Google account.{" "}
          <b>Owner</b>: manages everyone; set in the server's settings, so it cannot be changed here.{" "}
          <b>Admin</b>: adds and removes members, opens everything. <b>Member</b>: opens only the
          dashboards and Data pages ticked for them.
        </p>
      </div>
    </header>
  );

  if (!authRequired) {
    return (
      <>
        {header}
        <div className="wrap">
          <Empty title="Sign-in is switched off">
            Users apply once AUTH_REQUIRED=true. Until then every page is open to anyone who can reach it.
          </Empty>
        </div>
      </>
    );
  }
  if (!isAdmin) {
    return (
      <>
        {header}
        <div className="wrap"><Empty title="Admins only">Ask the owner if you need to add someone.</Empty></div>
      </>
    );
  }

  /** Mirrors the API: never the owner, never yourself, and admins only for the owner. */
  const editable = (u: UserRow) =>
    u.role !== "owner" && u.email !== me && (role === "owner" || u.role === "member");

  const act = (label: string, run: () => void) => {
    change.reset();
    if (label === "" || window.confirm(label)) run();
  };

  return (
    <>
      {header}
      <div className="wrap">
        <Section title="Add someone">
          <AddUser canMakeAdmin={role === "owner"} modules={modules.data ?? []} />
        </Section>

        <Section
          title="People with access"
          note={list.data ? `${list.data.filter((u) => u.active).length} active of ${list.data.length}` : undefined}
        >
          {change.isError ? <Band tone="warn">{change.error.message}</Band> : null}
          {list.isLoading ? <Spinner label="Loading users" /> : null}
          {list.isError ? <Band tone="warn">{list.error.message}</Band> : null}
          {list.data ? (
            <div className="tbl-wrap">
              <table className="users">
                <thead>
                  <tr>
                    <th className="txt">Person</th>
                    <th className="txt">Role</th>
                    <th className="txt">Can open</th>
                    <th className="txt">Status</th>
                    <th className="txt">Last signed in</th>
                    <th className="txt">Added by</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {list.data.map((u) => (
                    <Fragment key={u.email}>
                    <tr className={u.active ? undefined : "off"}>
                      <td className="txt">
                        <b>{u.name || u.email}</b>
                        {u.name ? <span className="em">{u.email}</span> : null}
                        {u.email === me ? <span className="you">you</span> : null}
                      </td>
                      <td className="txt">
                        {editable(u) && role === "owner" ? (
                          <select
                            value={u.role}
                            aria-label={`Role for ${u.email}`}
                            disabled={change.isPending}
                            onChange={(e) => act("", () =>
                              change.mutate({ method: "PATCH", email: u.email, body: { role: e.target.value } }))}
                          >
                            <option value="member">Member</option>
                            <option value="admin">Admin</option>
                          </select>
                        ) : (
                          <span className={`role ${u.role}`}>{ROLE_LABEL[u.role]}</span>
                        )}
                      </td>
                      <td className="txt can">
                        {u.role !== "member" ? (
                          <span className="all">Everything</span>
                        ) : (
                          <span>{opens(u, modules.data ?? [])}</span>
                        )}
                        {u.role === "member" && editable(u) && editing !== u.email ? (
                          <button type="button" className="link" onClick={() => { change.reset(); setEditing(u.email); }}>
                            Change
                          </button>
                        ) : null}
                      </td>
                      <td className="txt">{u.active ? "Active" : "Switched off"}</td>
                      <td className="txt">{u.last_sign_in_at ? when(u.last_sign_in_at) : "Never"}</td>
                      <td className="txt">{u.added_by ?? "—"}</td>
                      <td className="act">
                        {editable(u) ? (
                          <>
                            <button
                              type="button"
                              disabled={change.isPending}
                              onClick={() => act(
                                u.active ? `Switch off ${u.email}? They are signed out at their next click.` : "",
                                () => change.mutate({ method: "PATCH", email: u.email, body: { active: !u.active } }),
                              )}
                            >
                              {u.active ? "Switch off" : "Switch on"}
                            </button>{" "}
                            <button
                              type="button"
                              disabled={change.isPending}
                              onClick={() => act(`Remove ${u.email}? They will need adding again to sign in.`,
                                () => change.mutate({ method: "DELETE", email: u.email }))}
                            >
                              Remove
                            </button>
                          </>
                        ) : null}
                      </td>
                    </tr>
                    {editing === u.email ? (
                      <tr className="pick-row">
                        <td colSpan={7}>
                          <ModuleEditor
                            user={u}
                            modules={modules.data ?? []}
                            busy={change.isPending}
                            onCancel={() => setEditing(null)}
                            onSave={(next) => change.mutate(
                              { method: "PATCH", email: u.email, body: { modules: next } },
                              { onSuccess: () => setEditing(null) },
                            )}
                          />
                        </td>
                      </tr>
                    ) : null}
                    </Fragment>
                  ))}
                </tbody>
              </table>
            </div>
          ) : null}
        </Section>
      </div>
    </>
  );
}

/** "Pipeline, Commission, Downloads", or "Nothing yet". Keys whose dashboard
 *  has since gone are left out. */
function opens(u: UserRow, modules: ModuleInfo[]): string {
  const names = modules.filter((m) => u.modules.includes(m.key)).map((m) => m.name);
  return names.length ? names.join(", ") : "Nothing yet";
}

/** Checkboxes for every module, grouped as the menu groups them. */
function ModulePicker({ modules, value, onChange }: {
  modules: ModuleInfo[]; value: string[]; onChange: (next: string[]) => void;
}) {
  const toggle = (key: string) =>
    onChange(value.includes(key) ? value.filter((k) => k !== key) : [...value, key]);
  const groups = ["Dashboards", "Data"] as const;
  return (
    <div className="pick">
      {groups.map((group) => {
        const inGroup = modules.filter((m) => m.group === group);
        const all = inGroup.every((m) => value.includes(m.key));
        return (
          <fieldset key={group}>
            <legend>
              {group}{" "}
              <button
                type="button"
                className="link"
                onClick={() => onChange(all
                  ? value.filter((k) => !inGroup.some((m) => m.key === k))
                  : [...new Set([...value, ...inGroup.map((m) => m.key)])])}
              >
                {all ? "none" : "all"}
              </button>
            </legend>
            {inGroup.map((m) => (
              <label key={m.key}>
                <input type="checkbox" checked={value.includes(m.key)} onChange={() => toggle(m.key)} />
                {m.name}
              </label>
            ))}
          </fieldset>
        );
      })}
    </div>
  );
}

function ModuleEditor({ user, modules, busy, onSave, onCancel }: {
  user: UserRow; modules: ModuleInfo[]; busy: boolean;
  onSave: (next: string[]) => void; onCancel: () => void;
}) {
  const [value, setValue] = useState<string[]>(user.modules);
  return (
    <div className="pick-edit">
      <p>What <b>{user.name || user.email}</b> can open:</p>
      <ModulePicker modules={modules} value={value} onChange={setValue} />
      <div className="pick-act">
        <button type="button" className="btn" disabled={busy} onClick={() => onSave(value)}>
          {busy ? "Saving…" : "Save"}
        </button>{" "}
        <button type="button" disabled={busy} onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}

function AddUser({ canMakeAdmin, modules }: { canMakeAdmin: boolean; modules: ModuleInfo[] }) {
  const add = useUserChange();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");
  const [picked, setPicked] = useState<string[]>([]);

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const address = email.trim().toLowerCase();
    add.mutate(
      { method: "POST", body: { email: address, role, modules: role === "member" ? picked : [] } },
      { onSuccess: () => { setEmail(""); setPicked([]); } },
    );
  };

  return (
    <form className="user-add" onSubmit={submit}>
      <input
        type="email"
        required
        value={email}
        onChange={(e) => { setEmail(e.target.value); add.reset(); }}
        placeholder={`name@${SIGN_IN_DOMAIN}`}
        aria-label="Email address"
      />
      <select value={role} onChange={(e) => setRole(e.target.value as Role)} aria-label="Role">
        <option value="member">Member</option>
        {canMakeAdmin ? <option value="admin">Admin</option> : null}
      </select>
      <button type="submit" className="btn" disabled={add.isPending} aria-busy={add.isPending}>
        {add.isPending ? "Adding…" : "Add"}
      </button>
      {role === "member" ? (
        <div className="user-add-pick">
          <p>Can open{picked.length === 0 ? " (nothing ticked: they can sign in but see no dashboards)" : ""}:</p>
          <ModulePicker modules={modules} value={picked} onChange={(next) => { setPicked(next); add.reset(); }} />
        </div>
      ) : (
        <p className="status">Admins open every dashboard and Data page.</p>
      )}
      {add.isError ? <p className="status err">{add.error.message}</p> : null}
      {add.isSuccess ? <p className="status ok">Added. They can sign in now.</p> : null}
    </form>
  );
}
