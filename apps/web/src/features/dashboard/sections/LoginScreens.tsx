import type { Dispatch, FormEvent, SetStateAction } from "react";
import { LanguageSwitch } from "../components";
import type { DashboardText, Lang } from "../model";

type LoginState = { username: string; password: string };

export function LoadingScreen() {
  return (
    <main className="login">
      <section className="loginPanel">
        <p className="eyebrow">oslab control</p>
        <h1>Loading</h1>
      </section>
    </main>
  );
}

export function LoginScreen({
  t,
  lang,
  setLang,
  login,
  setLogin,
  notice,
  onSubmit,
}: {
  t: DashboardText;
  lang: Lang;
  setLang: (lang: Lang) => void;
  login: LoginState;
  setLogin: Dispatch<SetStateAction<LoginState>>;
  notice: string;
  onSubmit: () => void;
}) {
  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit();
  }

  return (
    <main className="login">
      <form className="loginPanel" onSubmit={submit}>
        <div className="languageLine">
          <p className="eyebrow">oslab control</p>
          <LanguageSwitch lang={lang} setLang={setLang} />
        </div>
        <h1>{t.signInTitle}</h1>
        <input autoComplete="username" placeholder={t.username} value={login.username} onChange={(event) => setLogin({ ...login, username: event.target.value })} />
        <input autoComplete="current-password" placeholder={t.password} type="password" value={login.password} onChange={(event) => setLogin({ ...login, password: event.target.value })} />
        <button type="submit">{t.signIn}</button>
        {notice && <p className="notice fail" role="alert">{notice}</p>}
        <p className="muted">{t.signInHint}</p>
      </form>
    </main>
  );
}
