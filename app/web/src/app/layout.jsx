import "pretendard/dist/web/variable/pretendardvariable-dynamic-subset.css";
import "@/styles/tokens.css";
import "./globals.css";

import { I18nProvider } from "@/components/i18n/I18nProvider";
import { ReplayProvider } from "@/components/replay/ReplayProvider";
import AppShell from "@/components/shell/AppShell";

export const metadata = {
  title: "DieCast-QA 재생 대시보드",
  description: "다이캐스팅 불량 예측·관리도·검사 운영을 과거 데이터로 재생하는 시뮬레이션",
};

export default function RootLayout({ children }) {
  return (
    <html lang="ko" data-theme="light" suppressHydrationWarning>
      <body>
        <I18nProvider>
          <ReplayProvider>
            <AppShell>{children}</AppShell>
          </ReplayProvider>
        </I18nProvider>
      </body>
    </html>
  );
}
