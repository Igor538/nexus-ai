import { useEffect, useRef, useState } from "react";
import { NavLink, Outlet, useLocation } from "react-router-dom";
import {
  Bell,
  Blocks,
  ChevronDown,
  Database,
  History,
  LayoutDashboard,
  LogOut,
  Menu,
  Settings,
  X,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { api } from "../lib/api";
import { formatRelative } from "../lib/utils";

const NAV_ITEMS = [
  { to: "/", label: "Painel", icon: LayoutDashboard, end: true },
  { to: "/workflows", label: "Automações", icon: Blocks },
  { to: "/executions", label: "Execuções", icon: History },
  { to: "/credentials", label: "Credenciais", icon: Database },
  { to: "/settings", label: "Ajustes", icon: Settings },
];

const TITLES: Array<{ match: RegExp; title: string; eyebrow: string }> = [
  { match: /^\/workflows\/\d+$/, title: "Editor de automação", eyebrow: "Automações" },
  { match: /^\/workflows/, title: "Automações", eyebrow: "Biblioteca" },
  { match: /^\/executions\/\d+/, title: "Detalhe da execução", eyebrow: "Execuções" },
  { match: /^\/executions/, title: "Execuções", eyebrow: "Histórico" },
  { match: /^\/credentials/, title: "Credenciais", eyebrow: "Segredos" },
  { match: /^\/settings/, title: "Ajustes", eyebrow: "Conta" },
  { match: /^\//, title: "Visão geral", eyebrow: "Painel" },
];

interface NotificationItem {
  id: number;
  title: string;
  body: string | null;
  level: string;
  execution_id: number | null;
  read: boolean;
  created_at: string;
}

export function AppShell() {
  const { user, logout } = useAuth();
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [userOpen, setUserOpen] = useState(false);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [unread, setUnread] = useState(0);
  const userRef = useRef<HTMLDivElement>(null);
  const notificationRef = useRef<HTMLDivElement>(null);

  const title = TITLES.find((item) => item.match.test(location.pathname));

  useEffect(() => {
    setMenuOpen(false);
    setUserOpen(false);
    setNotificationsOpen(false);
  }, [location.pathname]);

  useEffect(() => {
    let active = true;
    const load = () => {
      api
        .notifications()
        .then((response) => {
          if (!active) return;
          setNotifications(response.items);
          setUnread(response.unread);
        })
        .catch(() => undefined);
    };
    load();
    const timer = window.setInterval(load, 45_000);
    return () => {
      active = false;
      window.clearInterval(timer);
    };
  }, []);

  useEffect(() => {
    const onClick = (event: MouseEvent) => {
      if (notificationRef.current && !notificationRef.current.contains(event.target as Node)) {
        setNotificationsOpen(false);
      }
      if (userRef.current && !userRef.current.contains(event.target as Node)) {
        setUserOpen(false);
      }
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, []);

  async function markAllRead() {
    await api.markAllNotificationsRead().catch(() => undefined);
    setNotifications((current) => current.map((item) => ({ ...item, read: true })));
    setUnread(0);
  }

  return (
    <div className="shell">
      <aside className={`rail ${menuOpen ? "rail--open" : ""}`}>
        <div className="rail__brand">
          <div>
            <strong>Nexus</strong>
            <span>Automação com IA</span>
          </div>
          <button
            type="button"
            className="icon-button rail__close"
            onClick={() => setMenuOpen(false)}
            aria-label="Fechar menu"
          >
            <X size={18} />
          </button>
        </div>

        <nav className="rail__nav" aria-label="Navegação principal">
          <span className="rail__label">Workspace</span>
          {NAV_ITEMS.map((item) => (
            <NavLink
              key={item.to}
              to={item.to}
              end={item.end}
              className={({ isActive }) => `nav-link ${isActive ? "is-active" : ""}`}
            >
              <item.icon size={18} strokeWidth={1.8} />
              {item.label}
            </NavLink>
          ))}
        </nav>

        <div className="rail__footer">
          <div className="rail__note">
            <span className="signal-dot" aria-hidden="true" />
            Motor conectado
          </div>
          <a className="rail__hint" href="/health" target="_blank" rel="noreferrer">
            Status da API
          </a>
        </div>
      </aside>

      {menuOpen ? <div className="rail-scrim" onClick={() => setMenuOpen(false)} /> : null}

      <div className="shell__main">
        <header className="topbar">
          <div className="topbar__title">
            <button
              type="button"
              className="icon-button menu-toggle"
              onClick={() => setMenuOpen(true)}
              aria-label="Abrir menu"
            >
              <Menu size={20} />
            </button>
            <div>
              <span className="eyebrow">{title?.eyebrow ?? "Painel"}</span>
              <h1>{title?.title ?? "Visão geral"}</h1>
            </div>
          </div>

          <div className="topbar__actions">
            <div className="popover-anchor" ref={notificationRef}>
              <button
                type="button"
                className="icon-button"
                onClick={() => setNotificationsOpen((open) => !open)}
                aria-label={`Notificações${unread ? `, ${unread} não lidas` : ""}`}
                aria-expanded={notificationsOpen}
              >
                <Bell size={18} />
                {unread > 0 ? <span className="badge-dot">{unread > 9 ? "9+" : unread}</span> : null}
              </button>
              {notificationsOpen ? (
                <div className="popover popover--notifications">
                  <div className="popover__head">
                    <strong>Notificações</strong>
                    {unread > 0 ? (
                      <button type="button" className="link-button" onClick={markAllRead}>
                        Marcar tudo como lido
                      </button>
                    ) : null}
                  </div>
                  <div className="popover__list">
                    {notifications.length === 0 ? (
                      <p className="popover__empty">Nada por aqui. As execuções avisam quando terminam.</p>
                    ) : (
                      notifications.slice(0, 8).map((item) => (
                        <div
                          key={item.id}
                          className={`notice ${item.read ? "is-read" : ""} notice--${item.level}`}
                        >
                          <strong>{item.title}</strong>
                          {item.body ? <p>{item.body}</p> : null}
                          <span>{formatRelative(item.created_at)}</span>
                        </div>
                      ))
                    )}
                  </div>
                </div>
              ) : null}
            </div>

            <div className="popover-anchor" ref={userRef}>
              <button
                type="button"
                className="user-chip"
                onClick={() => setUserOpen((open) => !open)}
                aria-expanded={userOpen}
              >
                <span className="avatar">{(user?.name ?? "N").slice(0, 1).toUpperCase()}</span>
                <span className="user-chip__text">
                  <strong>{user?.name ?? "Visitante"}</strong>
                  <small>{user?.email ?? ""}</small>
                </span>
                <ChevronDown size={16} />
              </button>
              {userOpen ? (
                <div className="popover popover--user">
                  <NavLink to="/settings" className="popover__item">
                    <Settings size={16} /> Ajustes da conta
                  </NavLink>
                  <button type="button" className="popover__item" onClick={logout}>
                    <LogOut size={16} /> Sair
                  </button>
                </div>
              ) : null}
            </div>
          </div>
        </header>

        <main className="content">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
