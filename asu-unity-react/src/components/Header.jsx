import { ASUHeader } from "@asu/component-header-footer";
import asuLogoVertical from "../assets/asu-logo-vertical.png";
import asuLogoHorizontal from "../assets/asu-logo-horizontal.png";

// Required prop — not a partner, use a blank placeholder
const BLANK_GIF =
  "data:image/gif;base64,R0lGODlhAQABAIAAAAAAAP///yH5BAEAAAAALAAAAAABAAEAAAIBRAA7";

export default function Header({ casComplete = false, asurite = null }) {
  const navTree = [
    {
      href: "/",
      text: "Home",
      type: "icon-home",
      class: "home",
    },
    {
      href: "#verification-steps",
      text: "Steps",
    },
    {
      href: "#about",
      text: "About",
    },
  ];

  return (
    <ASUHeader
      logo={{
        src: asuLogoVertical,
        mobileSrc: asuLogoHorizontal,
        alt: "Arizona State University logo",
        title: "ASU homepage",
        brandLink: "https://www.asu.edu",
      }}
      partnerLogo={{ src: BLANK_GIF, alt: "" }}
      title="Devil2Devil"
      baseUrl="/"
      navTree={navTree}
      searchUrl="https://search.asu.edu/search"
      site="devil2devil-verification"
      loginLink={!casComplete ? "/auth/cas/login" : null}
      logoutLink={casComplete ? "/auth/logout" : null}
      loggedIn={casComplete}
      userName={casComplete && asurite ? asurite : ""}
      isPartner={false}
      expandOnHover={true}
      breakpoint="Lg"
    />
  );
}
