process.env.EXPO_PUBLIC_BACKEND_URL = "https://api.test";
jest.mock("@/src/utils/storage", () => {
  const mem = {};
  const sec = {};
  return {
    storage: {
      getItem: async (k, f) => (k in mem ? mem[k] : f),
      setItem: async (k, v) => ((mem[k] = v), true),
      removeItem: async (k) => (delete mem[k], true),
      secureGet: async (k, f) => (k in sec ? sec[k] : f),
      secureSet: async (k, v) => ((sec[k] = v), true),
      secureRemove: async (k) => (delete sec[k], true),
      __mem: mem,
      __sec: sec,
    },
  };
});
jest.mock("react-native-reanimated", () => {
  const { View } = require("react-native");
  const anim = { delay: () => anim, duration: () => anim };
  return { __esModule: true, default: { View }, View, FadeInDown: anim, FadeInUp: anim, FadeOutUp: anim };
});
jest.mock("react-native-worklets", () => ({}));
jest.mock("expo-router", () => ({ useRouter: () => ({ push: jest.fn(), replace: jest.fn(), back: jest.fn(), canGoBack: () => false }) }));
jest.mock("react-native-keyboard-controller", () => {
  const { View, ScrollView } = require("react-native");
  return { KeyboardAvoidingView: View, KeyboardAwareScrollView: ScrollView, KeyboardStickyView: View, KeyboardProvider: ({ children }) => children };
});
