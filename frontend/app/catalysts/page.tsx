/**
 * Page — /catalysts
 *
 * The catalysts calendar moved to the Today page's Calendar tab (UX overhaul
 * phase 2). Server-side redirect keeps old links/bookmarks working.
 */

import { redirect } from "next/navigation";

export default function CatalystsRedirect() {
  redirect("/?tab=calendar");
}
