import { ASUFooter } from "@asu/component-header-footer";
import asuLogoHorizontal from "../assets/asu-logo-horizontal.png";

export default function Footer() {
  return (
    <ASUFooter
      baseUrl="/"
      logo={{
        src: asuLogoHorizontal,
        alt: "Arizona State University",
        brandLink: "https://www.asu.edu",
      }}
      footerLinks={[
        [
          {
            href: "https://devil2devil.asu.edu",
            title: "About Devil2Devil",
          },
        ],
        [
          {
            href: "https://www.asu.edu/legal/copyright-trademark",
            title: "Terms of Use",
          },
          {
            href: "https://www.asu.edu/privacy",
            title: "Privacy",
          },
        ],
      ]}
      innovation={false}
      site="devil2devil-verification"
    />
  );
}
