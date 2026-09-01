import { adressesDuSite } from "@/lib/data/plan";
import { ADRESSE_DU_SITE } from "@/lib/site";
import { SITE } from "@/site.config";

/**
 * LE FLUX RSS, servi à /flux.xml.
 *
 * `force-static` est OBLIGATOIRE en export statique : sans lui, Next considère
 * cette route comme dynamique et refuse de construire. Avec, il écrit le
 * fichier une fois pendant le build.
 */
export const dynamic = "force-static";

/** Le XML n'a que cinq caractères interdits, mais aucun n'est facultatif. */
function echapper(texte: string): string {
  return texte
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&apos;");
}

export async function GET() {
  // Seules les entrées qui ont un titre méritent d'être annoncées : une page
  // sans titre dans un lecteur de flux n'est qu'une ligne vide.
  const entrees = (await adressesDuSite()).filter((a) => a.titre);

  const articles = entrees
    .map(
      (entree) => `    <item>
      <title>${echapper(entree.titre!)}</title>
      <link>${ADRESSE_DU_SITE}${entree.chemin}</link>
      <guid>${ADRESSE_DU_SITE}${entree.chemin}</guid>
      ${entree.resume ? `<description>${echapper(entree.resume)}</description>` : ""}
      ${entree.modifiee ? `<pubDate>${new Date(entree.modifiee).toUTCString()}</pubDate>` : ""}
    </item>`,
    )
    .join("\n");

  const flux = `<?xml version="1.0" encoding="UTF-8"?>
<rss version="2.0">
  <channel>
    <title>${echapper(SITE.nom)}</title>
    <link>${ADRESSE_DU_SITE}</link>
    <description>${echapper(SITE.description)}</description>
    <language>fr</language>
${articles}
  </channel>
</rss>`;

  return new Response(flux, {
    headers: { "Content-Type": "application/xml; charset=utf-8" },
  });
}
