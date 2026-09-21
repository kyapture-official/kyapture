import { createContext, useContext, useReducer, useCallback, useMemo } from "react";

const PixiesetCtx = createContext(null);

const initialState = {
  collection: {
    id: "",
    title: "",
    date: "",
    status: "DRAFT",
    coverImage: null,
    coverPhotoId: null,
    items: [],
    sets: [{ id: "all", name: "All Photos", count: 0 }],
    design: {
      coverLayout: "center",
      typographyFont: "serif",
      colorTheme: "light",
      gridStyle: "vertical",
      thumbSize: "regular",
      gridSpacing: 16,
    },
    settings: {
      customUrl: "",
      categoryTags: "",
      watermarkEnabled: false,
      autoExpiry: "",
      sliderEnabled: false,
      slideshowEnabled: false,
      downloadPin: "",
      favoritesEnabled: false,
      storeEnabled: false,
    },
  },
  isLoading: false,
  error: null,
  toasts: [],
};

function reducer(state, action) {
  switch (action.type) {
    case "SET_COLLECTION":
      return { ...state, collection: { ...state.collection, ...action.payload }, error: null };
    case "UPDATE_META":
      return { ...state, collection: { ...state.collection, ...action.payload } };
    case "SET_PHOTOS":
      return {
        ...state,
        collection: {
          ...state.collection,
          items: action.payload,
          sets: state.collection.sets.map((s) =>
            s.id === "all" ? { ...s, count: action.payload.length } : s
          ),
        },
      };
    case "ADD_PHOTOS":
      return {
        ...state,
        collection: {
          ...state.collection,
          items: [...state.collection.items, ...action.payload],
          sets: state.collection.sets.map((s) =>
            s.id === "all"
              ? { ...s, count: s.count + action.payload.length }
              : s
          ),
        },
      };
    case "REMOVE_PHOTO":
      return {
        ...state,
        collection: {
          ...state.collection,
          items: state.collection.items.filter((p) => p.id !== action.payload),
          sets: state.collection.sets.map((s) =>
            s.id === "all"
              ? { ...s, count: Math.max(0, s.count - 1) }
              : s
          ),
        },
      };
    case "SET_COVER":
      return {
        ...state,
        collection: {
          ...state.collection,
          coverPhotoId: action.payload.id,
          coverImage: action.payload.url,
        },
      };
    case "ADD_SET":
      return {
        ...state,
        collection: {
          ...state.collection,
          sets: [...state.collection.sets, action.payload],
        },
      };
    case "UPDATE_DESIGN":
      return {
        ...state,
        collection: {
          ...state.collection,
          design: { ...state.collection.design, ...action.payload },
        },
      };
    case "UPDATE_SETTINGS":
      return {
        ...state,
        collection: {
          ...state.collection,
          settings: { ...state.collection.settings, ...action.payload },
        },
      };
    case "PUBLISH":
      return {
        ...state,
        collection: { ...state.collection, status: "PUBLISHED" },
      };
    case "UNPUBLISH":
      return {
        ...state,
        collection: { ...state.collection, status: "DRAFT" },
      };
    case "SET_LOADING":
      return { ...state, isLoading: action.payload };
    case "SET_ERROR":
      return { ...state, error: action.payload };
    case "ADD_TOAST":
      return { ...state, toasts: [...state.toasts, { id: Date.now(), ...action.payload }] };
    case "REMOVE_TOAST":
      return { ...state, toasts: state.toasts.filter((t) => t.id !== action.payload) };
    default:
      return state;
  }
}

export function PixiesetProvider({ children }) {
  const [state, dispatch] = useReducer(reducer, initialState);

  const updateCollectionMeta = useCallback(
    (meta) => dispatch({ type: "UPDATE_META", payload: meta }),
    []
  );

  const addPhotos = useCallback(
    (photos) => dispatch({ type: "ADD_PHOTOS", payload: photos }),
    []
  );

  const setPhotos = useCallback(
    (photos) => dispatch({ type: "SET_PHOTOS", payload: photos }),
    []
  );

  const removePhoto = useCallback(
    (id) => dispatch({ type: "REMOVE_PHOTO", payload: id }),
    []
  );

  const setCover = useCallback(
    (id, url) => dispatch({ type: "SET_COVER", payload: { id, url } }),
    []
  );

  const createSet = useCallback(
    (set) =>
      dispatch({
        type: "ADD_SET",
        payload: { id: `set-${Date.now()}`, name: set.name, count: 0 },
      }),
    []
  );

  const updateDesign = useCallback(
    (settings) => dispatch({ type: "UPDATE_DESIGN", payload: settings }),
    []
  );

  const updateSettings = useCallback(
    (settings) => dispatch({ type: "UPDATE_SETTINGS", payload: settings }),
    []
  );

  const publishCollection = useCallback(
    () => dispatch({ type: "PUBLISH" }),
    []
  );

  const unpublishCollection = useCallback(
    () => dispatch({ type: "UNPUBLISH" }),
    []
  );

  const addToast = useCallback(
    (toast) => dispatch({ type: "ADD_TOAST", payload: toast }),
    []
  );

  const removeToast = useCallback(
    (id) => dispatch({ type: "REMOVE_TOAST", payload: id }),
    []
  );

  const value = useMemo(
    () => ({
      ...state,
      updateCollectionMeta,
      addPhotos,
      setPhotos,
      removePhoto,
      setCover,
      createSet,
      updateDesign,
      updateSettings,
      publishCollection,
      unpublishCollection,
      addToast,
      removeToast,
      dispatch,
    }),
    [
      state,
      updateCollectionMeta,
      addPhotos,
      setPhotos,
      removePhoto,
      setCover,
      createSet,
      updateDesign,
      updateSettings,
      publishCollection,
      unpublishCollection,
      addToast,
      removeToast,
    ]
  );

  return <PixiesetCtx.Provider value={value}>{children}</PixiesetCtx.Provider>;
}

export function usePixieset() {
  const ctx = useContext(PixiesetCtx);
  if (!ctx) throw new Error("usePixieset must be used within PixiesetProvider");
  return ctx;
}
