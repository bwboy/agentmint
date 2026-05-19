import { LoginForm } from "@/components/auth/LoginForm";

export default function LoginPage() {
  return (
    <div className="max-w-md mx-auto px-4 py-16">
      <div className="bg-white rounded-2xl border border-gray-100 p-8">
        <h1 className="text-xl font-semibold mb-1">登录 / 注册</h1>
        <p className="text-sm text-gray-400 mb-6">手机号验证码登录，新用户自动注册</p>
        <LoginForm />
      </div>
    </div>
  );
}
