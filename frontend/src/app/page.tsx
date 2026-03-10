import { createClient } from "@/lib/supabase/server"
import { redirect } from "next/navigation"
import HomeUI from "@/components/HomeUI"

export default async function Home() {
  const supabase = await createClient()
  const { data: { user } } = await supabase.auth.getUser()
  if (user) redirect("/dashboard")

  return <HomeUI />
}
