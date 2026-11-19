import { Suspense } from "react";

import AlarmsView from "@/components/views/AlarmsView";

export const metadata = { title: "알람 센터 · DieCast-QA" };

export default function Page() {
  return (
    <Suspense fallback={null}>
      <AlarmsView />
    </Suspense>
  );
}
