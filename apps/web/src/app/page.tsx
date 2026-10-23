"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { Spinner } from "@/components/ui/feedback";
import { ApiError } from "@/lib/api";
import { useMe } from "@/lib/queries";
import { LAST_WORKSPACE_KEY, readLocal } from "@/lib/storage";

export default function Home() {
  const router = useRouter();
  const me = useMe();

  useEffect(() => {
    if (me.error instanceof ApiError && me.error.status === 401) {
      router.replace("/login");
      return;
    }
    if (!me.data) return;
    const last = readLocal(LAST_WORKSPACE_KEY);
    const slugs = me.data.workspaces.map((w) => w.slug);
    const target = last && slugs.includes(last) ? last : slugs[0];
    router.replace(target ? `/w/${target}/chat` : "/welcome");
  }, [me.data, me.error, router]);

  return (
    <main className="flex min-h-dvh items-center justify-center">
      <Spinner className="size-5" />
    </main>
  );
}
