import { LoginForm } from "@/components/auth/LoginForm";

export default function LoginPage() {
  return (
    <div className="mx-auto max-w-md px-4 py-12">
      <div className="surface-card relative overflow-hidden p-8">
        <div className="hero-grid pointer-events-none absolute inset-x-0 top-0 h-32 opacity-60" />
        <div className="relative">
          <p className="text-sm font-medium text-brand">Account Access</p>
          <h1 className="mt-2 text-2xl font-semibold text-ink">登录 / 注册</h1>
          <p className="mb-6 mt-2 text-sm leading-6 text-text-secondary">手机号验证码登录，新用户自动注册。正式云上部署前会继续使用 mock 验证码。</p>
        </div>
        <LoginForm />
      </div>
    </div>
  );
}
