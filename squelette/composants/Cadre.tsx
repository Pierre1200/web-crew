/**
 * LE CADRE EN POINTILLÉS : la place d'une image qui n'existe pas encore.
 *
 * Il tient exactement la place de la future photo, donc rien ne bouge le jour
 * où elle arrive. Sa légende est une COMMANDE DE PRISE DE VUE : elle dit ce
 * qu'il faut photographier, à qui lira la page comme à qui tient l'appareil.
 *
 * Un composant plutôt qu'un bloc recopié : sur le site de référence, ce cadre
 * était collé à l'identique à quatre endroits. Recopié par une machine, c'est
 * quatre occasions de diverger.
 */
export function Cadre({
  format = "4x3",
  legende,
}: {
  format?: "4x3" | "16x10" | "1x1";
  legende?: string;
}) {
  return (
    <figure className={`cadre cadre--${format}`}>
      <div className="cadre__zone" aria-hidden="true">
        <svg viewBox="0 0 48 36" className="cadre__icone" aria-hidden="true">
          <rect x="2" y="4" width="44" height="30" rx="3" fill="none" stroke="currentColor" strokeWidth="2.2" />
          <circle cx="15" cy="15" r="4" fill="currentColor" />
          <path d="M6 30 L20 18 L28 25 L35 20 L44 29" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinejoin="round" />
        </svg>
      </div>
      {legende && <figcaption className="cadre__legende">{legende}</figcaption>}
    </figure>
  );
}
