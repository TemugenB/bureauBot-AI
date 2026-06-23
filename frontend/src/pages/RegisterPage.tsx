import { useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Container } from "@/components/Container";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api";
import { setToken } from "@/lib/auth";

export function RegisterPage() {
  const navigate = useNavigate();
  const [username, setUsername] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(false);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError("");
    setLoading(true);
    try {
      const res = await api.post<{ access_token: string }>("/auth/register", { username, email, password });
      setToken(res.access_token);
      navigate("/");
    } catch (err: any) {
      if (err?.data?.detail) {
        if (Array.isArray(err.data.detail)) {
          setError(err.data.detail.map((d: any) => d.msg).join(". "));
        } else {
          setError(err.data.detail);
        }
      } else {
        setError("Registration failed. Please try again.");
      }
    }
    setLoading(false);
  };

  return (
    <Container className="flex min-h-screen items-center justify-center">
      <div className="w-full max-w-sm">
        <div className="text-center">
          <span className="inline-flex h-12 w-12 items-center justify-center rounded-md bg-primary text-primary-foreground text-xl font-bold">B</span>
          <h1 className="mt-4 text-2xl font-bold text-foreground">Create account</h1>
        </div>
        <form onSubmit={handleSubmit} className="mt-8 space-y-4">
          <Input value={username} onChange={(e) => setUsername(e.target.value)} placeholder="Username" required />
          <Input type="email" value={email} onChange={(e) => setEmail(e.target.value)} placeholder="Email" required />
          <Input type="password" value={password} onChange={(e) => setPassword(e.target.value)} placeholder="Password (min 6 chars)" required />
          {error && <p className="text-sm text-destructive">{error}</p>}
          <Button type="submit" className="w-full" disabled={loading}>{loading ? "Creating..." : "Create account"}</Button>
        </form>
        <p className="mt-4 text-center text-sm text-muted-foreground">
          Already have an account? <Link to="/login" className="text-primary hover:underline">Sign in</Link>
        </p>
      </div>
    </Container>
  );
}
