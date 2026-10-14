import { useState } from "react";
import type { FormEvent } from "react";

import { useUserChange, useUsers } from "../api/client";
import type { UserRow } from "../api/types";
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
  const change = useUserChange();

  const header = (
    <header className="top">
      <div className="top-in">
        <h1>Users</h1>
        <p className="sub">
          Only the people listed here can sign in, with their @{SIGN_IN_DOMAIN} Google account.{" "}
          <b>Owner</b>: manages everyone; set in the server's settings, so it cannot be changed here.{" "}
          <b>Admin</b>: adds and removes members. <b>Member</b>: uses the dashboards.
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
          <AddUser canMakeAdmin={role === "owner"} />
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
                    <th className="txt">Status</th>
                    <th className="txt">Last signed in</th>
                    <th className="txt">Added by</th>
                    <th />
                  </tr>
                </thead>
                <tbody>
                  {list.data.map((u) => (
                    <tr key={u.email} className={u.active ? undefined : "off"}>
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

function AddUser({ canMakeAdmin }: { canMakeAdmin: boolean }) {
  const add = useUserChange();
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<Role>("member");

  const submit = (event: FormEvent) => {
    event.preventDefault();
    const address = email.trim().toLowerCase();
    add.mutate({ method: "POST", body: { email: address, role } }, { onSuccess: () => setEmail("") });
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
      {add.isError ? <p className="status err">{add.error.message}</p> : null}
      {add.isSuccess ? <p className="status ok">Added. They can sign in now.</p> : null}
    </form>
  );
}
