import { redirect } from "next/navigation";

export default function RootPage() {
  // The intro page lives inside the authenticated shell, so signed-out visitors
  // are bounced to /login by that layout.
  redirect("/home");
}
