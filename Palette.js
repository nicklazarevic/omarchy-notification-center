function linear(value) {
  return value <= 0.04045 ? value / 12.92 : Math.pow((value + 0.055) / 1.055, 2.4)
}

// Choose the higher-contrast text for any Omarchy accent, including light themes.
function onAccent(color) {
  var luminance = 0.2126 * linear(color.r) + 0.7152 * linear(color.g) + 0.0722 * linear(color.b)
  return luminance > 0.179 ? "#000000" : "#ffffff"
}
