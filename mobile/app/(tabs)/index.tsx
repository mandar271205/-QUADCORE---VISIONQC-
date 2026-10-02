import React, { useState, useRef, useEffect } from 'react';
import {
  View, Text, StyleSheet, TouchableOpacity, Image,
  ScrollView, ActivityIndicator, Alert, Platform
} from 'react-native';
import { CameraView, CameraType, useCameraPermissions } from 'expo-camera';
import * as ImagePicker from 'expo-image-picker';
import * as Haptics from 'expo-haptics';
import { BlurView } from 'expo-blur';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Button, Card, ActivityIndicator as PaperActivityIndicator, MD3DarkTheme, Provider as PaperProvider } from 'react-native-paper';
import { runInspection, getProducts } from '../../src/api';
import type { InspectionResponse, Product } from '../../src/types';

const COLORS = {
  bg: '#0F172A',
  surface: '#1E293B',
  panel: '#1E293B',
  border: '#334155',
  text: '#F8FAFC',
  muted: '#94A3B8',
  pass: '#22C55E',
  fail: '#EF4444',
  review: '#F59E0B',
  accent: '#06B6D4',
};

const decisionColors = {
  PASS: { bg: 'rgba(34,197,94,0.15)', text: COLORS.pass, border: 'rgba(34,197,94,0.3)' },
  FAIL: { bg: 'rgba(239,68,68,0.15)', text: COLORS.fail, border: 'rgba(239,68,68,0.3)' },
  REVIEW: { bg: 'rgba(245,158,11,0.15)', text: COLORS.review, border: 'rgba(245,158,11,0.3)' },
};

type Stage = 'idle' | 'camera' | 'preview' | 'inspecting' | 'result' | 'error';

export default function InspectScreen() {
  const [stage, setStage] = useState<Stage>('idle');
  const [permission, requestPermission] = useCameraPermissions();
  const [facing, setFacing] = useState<CameraType>('back');
  const cameraRef = useRef<CameraView>(null);

  const [capturedUri, setCapturedUri] = useState<string | null>(null);
  const [result, setResult] = useState<InspectionResponse | null>(null);
  const [error, setError] = useState('');
  const [products, setProducts] = useState<Product[]>([]);
  const [selectedProduct, setSelectedProduct] = useState<string>('');

  useEffect(() => {
    getProducts().then(setProducts).catch(() => {});
  }, []);

  const capture = async () => {
    if (!cameraRef.current) return;
    try {
      const photo = await cameraRef.current.takePictureAsync({ quality: 0.85 });
      if (photo?.uri) {
        setCapturedUri(photo.uri);
        setStage('preview');
        Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
      }
    } catch (e) {
      Alert.alert('Error', 'Could not capture photo.');
    }
  };

  const pickImage = async () => {
    const { granted } = await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!granted) { Alert.alert('Permission required', 'Photo library access needed.'); return; }
    const result = await ImagePicker.launchImageLibraryAsync({
      mediaTypes: ImagePicker.MediaTypeOptions.Images,
      quality: 0.85,
    });
    if (!result.canceled && result.assets[0]) {
      setCapturedUri(result.assets[0].uri);
      setStage('preview');
    }
  };

  const inspect = async () => {
    if (!capturedUri) return;
    setStage('inspecting');
    setError('');
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium);
    try {
      const res = await runInspection(capturedUri, selectedProduct || undefined);
      setResult(res);
      setStage('result');
      const feedback =
        res.decision === 'PASS'
          ? Haptics.NotificationFeedbackType.Success
          : res.decision === 'FAIL'
          ? Haptics.NotificationFeedbackType.Error
          : Haptics.NotificationFeedbackType.Warning;
      Haptics.notificationAsync(feedback);
    } catch (e: any) {
      setError(e.message || 'Inspection failed. Please try again.');
      setStage('error');
    }
  };

  const reset = () => {
    setStage('idle');
    setCapturedUri(null);
    setResult(null);
    setError('');
  };

  // Camera permission flow
  if (stage === 'camera') {
    if (!permission?.granted) {
      return (
        <View style={[styles.container, { justifyContent: 'center', padding: 32 }]}>
          <Text style={styles.text}>Camera access required.</Text>
          <TouchableOpacity style={styles.btnPrimary} onPress={requestPermission}>
            <Text style={styles.btnText}>Grant Permission</Text>
          </TouchableOpacity>
        </View>
      );
    }
    return (
      <View style={{ flex: 1, backgroundColor: '#000' }}>
        <CameraView ref={cameraRef} style={{ flex: 1 }} facing={facing}>
          {/* Grid overlay */}
          <View style={styles.cameraOverlay}>
            <View style={styles.cameraFrame} />
          </View>
        </CameraView>
        {/* Controls */}
        <BlurView intensity={80} tint="dark" style={styles.cameraControls}>
          <TouchableOpacity onPress={pickImage} style={styles.cameraBtn}>
            <Text style={[styles.muted, { fontSize: 12, color: '#fff' }]}>Gallery</Text>
          </TouchableOpacity>
          <TouchableOpacity onPress={capture} style={styles.captureBtn} />
          <TouchableOpacity
            onPress={() => setFacing(f => f === 'back' ? 'front' : 'back')}
            style={styles.cameraBtn}
          >
            <Text style={[styles.muted, { fontSize: 12, color: '#fff' }]}>Flip</Text>
          </TouchableOpacity>
        </BlurView>
        <TouchableOpacity onPress={() => setStage('idle')} style={styles.backBtn}>
          <BlurView intensity={50} tint="dark" style={{ paddingHorizontal: 16, paddingVertical: 8, borderRadius: 20 }}>
            <Text style={{ color: '#fff', fontSize: 14, fontWeight: '600' }}>✕ Cancel</Text>
          </BlurView>
        </TouchableOpacity>
      </View>
    );
  }

  return (
    <PaperProvider theme={MD3DarkTheme}>
    <SafeAreaView style={styles.container} edges={['bottom']}>
      <ScrollView contentContainerStyle={styles.scroll}>

        {/* Product selector */}
        {products.length > 0 && (
          <View style={styles.card}>
            <Text style={styles.label}>PRODUCT</Text>
            <ScrollView horizontal showsHorizontalScrollIndicator={false}>
              <View style={{ flexDirection: 'row', gap: 8 }}>
                <TouchableOpacity
                  onPress={() => setSelectedProduct('')}
                  style={[styles.productChip, !selectedProduct && styles.productChipActive]}
                >
                  <Text style={[styles.chipText, !selectedProduct && { color: COLORS.accent }]}>
                    Any Product
                  </Text>
                </TouchableOpacity>
                {products.map(p => (
                  <TouchableOpacity
                    key={p.id}
                    onPress={() => setSelectedProduct(p.id)}
                    style={[styles.productChip, selectedProduct === p.id && styles.productChipActive]}
                  >
                    <Text style={[styles.chipText, selectedProduct === p.id && { color: COLORS.accent }]}>
                      {p.name}
                    </Text>
                  </TouchableOpacity>
                ))}
              </View>
            </ScrollView>
          </View>
        )}

        {/* Preview image */}
        {capturedUri && (stage === 'preview' || stage === 'inspecting' || stage === 'result' || stage === 'error') && (
          <View style={styles.card}>
            <Image source={{ uri: capturedUri }} style={styles.previewImage} resizeMode="contain" />
          </View>
        )}

        {/* Inspecting indicator */}
        {stage === 'inspecting' && (
          <View style={[styles.card, { alignItems: 'center', paddingVertical: 32 }]}>
            <PaperActivityIndicator animating={true} size="large" color={COLORS.accent} />
            <Text style={[styles.text, { marginTop: 16, fontWeight: '600' }]}>Inspecting unit...</Text>
            <Text style={[styles.muted, { marginTop: 8, fontSize: 13 }]}>Analyzing image quality</Text>
          </View>
        )}

        {/* Result */}
        {stage === 'result' && result && (
          <>
            <View style={styles.card}>
              <View style={[
                styles.decisionBadge,
                { backgroundColor: decisionColors[result.decision].bg, borderColor: decisionColors[result.decision].border }
              ]}>
                <Text style={[styles.decisionText, { color: decisionColors[result.decision].text }]}>
                  {result.decision}
                </Text>
              </View>
              {result.summary ? (
                <Text style={[styles.muted, { marginTop: 12, textAlign: 'center', lineHeight: 20 }]}>
                  {result.summary}
                </Text>
              ) : null}
            </View>

            {/* Scores */}
            <View style={styles.scoreRow}>
              {[
                { label: 'Anomaly', value: `${(result.anomaly_score * 100).toFixed(1)}%` },
                { label: 'Confidence', value: `${(result.confidence * 100).toFixed(1)}%` },
                { label: 'Time', value: `${result.processing_time_ms}ms` },
              ].map(({ label, value }) => (
                <View key={label} style={[styles.scoreCard, { flex: 1 }]}>
                  <Text style={styles.scoreValue}>{value}</Text>
                  <Text style={styles.scoreLabel}>{label}</Text>
                </View>
              ))}
            </View>

            {/* Heatmap */}
            {result.heatmap_url && (
              <View style={styles.card}>
                <Text style={styles.label}>ANOMALY HEATMAP</Text>
                <Image source={{ uri: result.heatmap_url }} style={styles.heatmapImage} resizeMode="contain" />
              </View>
            )}

            {/* Defects */}
            {result.defects.length > 0 && (
              <View style={styles.card}>
                <Text style={styles.label}>DETECTED DEVIATIONS ({result.defects.length})</Text>
                {result.defects.map((d, i) => (
                  <View key={i} style={styles.defectItem}>
                    <View style={{ flexDirection: 'row', justifyContent: 'space-between', marginBottom: 4 }}>
                      <Text style={[styles.text, { fontWeight: '600', fontSize: 14 }]}>
                        {d.type.replace(/_/g, ' ')}
                      </Text>
                      <Text style={[styles.text, { fontSize: 12, textTransform: 'uppercase',
                        color: d.severity === 'high' ? COLORS.fail : d.severity === 'medium' ? COLORS.review : COLORS.muted
                      }]}>
                        {d.severity}
                      </Text>
                    </View>
                    {d.description && (
                      <Text style={[styles.muted, { fontSize: 13, lineHeight: 18 }]}>{d.description}</Text>
                    )}
                  </View>
                ))}
              </View>
            )}
          </>
        )}

        {/* Error */}
        {stage === 'error' && (
          <View style={[styles.card, { borderColor: 'rgba(239,68,68,0.3)', backgroundColor: 'rgba(239,68,68,0.08)' }]}>
            <Text style={{ color: COLORS.fail, fontSize: 14, lineHeight: 20 }}>{error}</Text>
          </View>
        )}

        {/* Action buttons */}
        <View style={{ gap: 10, marginTop: 4 }}>
          {stage === 'idle' && (
            <>
              <Button mode="contained" buttonColor={COLORS.accent} textColor="#fff" onPress={() => setStage('camera')} style={{ borderRadius: 8 }}>
                📷 Open Camera
              </Button>
              <Button mode="outlined" textColor={COLORS.text} onPress={pickImage} style={{ borderRadius: 8, borderColor: COLORS.border }}>
                ⬆ Upload from Gallery
              </Button>
            </>
          )}
          {(stage === 'preview' || stage === 'error') && (
            <>
              <Button mode="contained" buttonColor={COLORS.accent} textColor="#fff" onPress={inspect} style={{ borderRadius: 8 }}>
                🔍 INSPECT UNIT
              </Button>
              <Button mode="outlined" textColor={COLORS.text} onPress={reset} style={{ borderRadius: 8, borderColor: COLORS.border }}>
                ↩ Retake
              </Button>
            </>
          )}
          {stage === 'result' && (
            <Button mode="outlined" textColor={COLORS.text} onPress={reset} style={{ borderRadius: 8, borderColor: COLORS.border }}>
              ↩ Inspect Next Unit
            </Button>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
    </PaperProvider>
  );
}

const styles = StyleSheet.create({
  container: { flex: 1, backgroundColor: COLORS.bg },
  scroll: { padding: 16, gap: 12, paddingBottom: 32 },
  card: {
    backgroundColor: COLORS.surface,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: COLORS.border,
    padding: 16,
  },
  label: { color: COLORS.muted, fontSize: 10, fontWeight: '600', letterSpacing: 1, marginBottom: 10, textTransform: 'uppercase' },
  text: { color: COLORS.text, fontSize: 14 },
  muted: { color: COLORS.muted, fontSize: 14 },

  productChip: {
    paddingHorizontal: 12, paddingVertical: 6,
    borderRadius: 20, borderWidth: 1, borderColor: COLORS.border,
    backgroundColor: COLORS.panel,
  },
  productChipActive: { borderColor: COLORS.accent, backgroundColor: 'rgba(59,130,246,0.15)' },
  chipText: { color: COLORS.muted, fontSize: 13, fontWeight: '500' },

  previewImage: { width: '100%', height: 240, borderRadius: 8 },
  heatmapImage: { width: '100%', height: 200, borderRadius: 8, marginTop: 8 },

  decisionBadge: {
    alignSelf: 'center', paddingHorizontal: 32, paddingVertical: 14,
    borderRadius: 50, borderWidth: 1,
  },
  decisionText: { fontSize: 22, fontWeight: '800', letterSpacing: 3 },

  scoreRow: { flexDirection: 'row', gap: 10 },
  scoreCard: {
    backgroundColor: COLORS.surface, borderRadius: 12, borderWidth: 1,
    borderColor: COLORS.border, padding: 14, alignItems: 'center',
  },
  scoreValue: { color: COLORS.text, fontSize: 20, fontWeight: '700' },
  scoreLabel: { color: COLORS.muted, fontSize: 11, marginTop: 4, textTransform: 'uppercase', letterSpacing: 0.5 },

  defectItem: {
    backgroundColor: COLORS.panel, borderRadius: 8, padding: 12, marginTop: 8,
  },

  btnPrimary: {
    backgroundColor: COLORS.accent, borderRadius: 10,
    paddingVertical: 14, alignItems: 'center',
  },
  btnSecondary: {
    backgroundColor: COLORS.panel, borderRadius: 10, borderWidth: 1,
    borderColor: COLORS.border, paddingVertical: 14, alignItems: 'center',
  },
  btnText: { color: '#fff', fontWeight: '600', fontSize: 15 },

  // Camera
  cameraOverlay: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  cameraFrame: {
    width: 280, height: 280,
    borderWidth: 2, borderColor: 'rgba(59,130,246,0.7)', borderRadius: 12,
  },
  cameraControls: {
    flexDirection: 'row', justifyContent: 'space-around', alignItems: 'center',
    backgroundColor: 'rgba(0,0,0,0.8)', paddingVertical: 24, paddingHorizontal: 20,
  },
  captureBtn: {
    width: 70, height: 70, borderRadius: 35,
    backgroundColor: '#fff', borderWidth: 4, borderColor: 'rgba(255,255,255,0.5)',
  },
  cameraBtn: { width: 60, alignItems: 'center' },
  backBtn: {
    position: 'absolute', top: 50, left: 20,
    borderRadius: 20, overflow: 'hidden',
  },
});
