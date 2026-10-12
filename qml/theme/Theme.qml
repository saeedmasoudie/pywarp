pragma Singleton

import QtQuick

QtObject {
    readonly property SystemPalette systemPalette: SystemPalette {}
    readonly property bool aurora: AppController.theme === "aurora"
    readonly property bool dark: AppController.theme === "dark" || aurora
        || (AppController.theme === "system"
            && systemPalette.window.hslLightness < 0.5)

    readonly property color background: aurora ? "#0A1020"
        : dark ? "#080A12" : "#F4F5FA"
    readonly property color backgroundElevated: aurora ? "#0E172A"
        : dark ? "#0B0E18" : "#FFFFFF"
    readonly property color sidebar: aurora ? "#0C1426"
        : dark ? "#0A0D16" : "#FBFBFE"
    readonly property color surface: aurora ? "#111C32"
        : dark ? "#101420" : "#FFFFFF"
    readonly property color surfaceRaised: aurora ? "#17233D"
        : dark ? "#151A29" : "#F7F7FC"
    readonly property color surfaceBright: aurora ? "#1E2E4E"
        : dark ? "#1B2234" : "#EEEFF7"
    readonly property color surfaceHover: aurora ? "#263A60"
        : dark ? "#20283B" : "#E8EAF4"
    readonly property color border: aurora ? "#293B5F"
        : dark ? "#252D42" : "#DEE1ED"
    readonly property color borderBright: aurora ? "#3B5685"
        : dark ? "#3B4561" : "#C7CCDE"
    readonly property color text: aurora ? "#F3F7FF"
        : dark ? "#F5F6FB" : "#161825"
    readonly property color textMuted: aurora ? "#A6B4CD"
        : dark ? "#929BB2" : "#686F83"
    readonly property color textFaint: aurora ? "#6F82A3"
        : dark ? "#5F687E" : "#989FB0"
    readonly property color accent: aurora ? "#8B7CFF" : "#7667F5"
    readonly property color accentHover: aurora ? "#A89EFF" : "#9187FF"
    readonly property color accentSoft: aurora ? "#2B285B"
        : dark ? "#262148" : "#ECE9FF"
    readonly property color accentFaint: aurora ? "#1B1C3E"
        : dark ? "#191631" : "#F6F4FF"
    readonly property color secondary: aurora ? "#48D9B7" : "#32D4C2"
    readonly property color secondarySoft: aurora ? "#153A38"
        : dark ? "#12322F" : "#DFF9F5"
    readonly property color success: "#42D392"
    readonly property color successSoft: dark ? "#123128" : "#E1F8ED"
    readonly property color warning: "#F5B942"
    readonly property color danger: "#FF657A"
    readonly property color dangerSoft: dark ? "#381820" : "#FFE7EB"
    readonly property color blue: "#42A5FF"
    readonly property color cloudflare: "#F48120"

    readonly property int radiusSmall: 10
    readonly property int radius: 14
    readonly property int radiusLarge: 20
    readonly property int radiusPill: 999
    readonly property int space: 12
    readonly property int pageMargin: 26
    readonly property int animationFast: 140
    readonly property int animation: 240
}
