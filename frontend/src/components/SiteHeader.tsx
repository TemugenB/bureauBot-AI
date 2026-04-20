import { Link, useLocation, useNavigate } from "react-router-dom";
import { cn } from "@/lib/utils";
import { clearToken } from "@/lib/auth";

export function SiteHeader() {
  const { pathname } = useLocation();
  const navigate = useNavigate();

  return (
    <header className="sticky top-0 z-40 w-full border-b border-border bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
      <div className="mx-auto flex h-16 w-full max-w-6xl items-center justify-between px-4 sm:px-6 lg:px-8">
        <Link to="/" className="flex items-center gap-2">
          <span className="flex h-8 w-8 items-center justify-center rounded-md bg-primary text-primary-foreground font-bold">B</span>
          <span className="text-base font-semibold tracking-tight text-foreground sm:text-lg">Bureaucracy Navigator</span>
        </Link>
        <nav className="flex items-center gap-1 sm:gap-2">
          <NavLink to="/" current={pathname === "/"}>Home</NavLink>
          <NavLink to="/sources" current={pathname === "/sources"}>Sources</NavLink>
          <button
            onClick={() => { clearToken(); navigate("/login"); }}
            className="rounded-md px-3 py-2 text-sm font-medium text-muted-foreground transition-colors hover:bg-accent hover:text-foreground"
          >
            Logout
          </button>
        </nav>
      </div>
    </header>
  );
}

function NavLink({ to, current, children }: { to: string; current: boolean; children: React.ReactNode }) {
  return (
    <Link to={to} className={cn(
      "rounded-md px-3 py-2 text-sm font-medium transition-colors",
      current ? "bg-accent text-foreground" : "text-muted-foreground hover:bg-accent hover:text-foreground",
    )}>{children}</Link>
  );
}
