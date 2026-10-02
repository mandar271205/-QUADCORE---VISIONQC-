import React, { useEffect, useState } from 'react';
import {
  View,
  Text,
  StyleSheet,
  ScrollView,
  Image,
  TouchableOpacity,
  ActivityIndicator,
  Alert,
} from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { SafeAreaView } from 'react-native-safe-area-context';
import { getInspection, deleteInspection } from '../../src/api';
import type { InspectionResponse, Decision } from '../../src/types';

const COLORS = {
  bg: '#0f1117',
  surface: '#1a1d27',
  panel: '#21263a',
  border: '#2d3348',
  text: '#e2e8f0',
  muted: '#8b92a5',
  accent: '#3b82f6',
  pass: '#22c55e',
  fail: '#ef4444',
  review: '#f59e0b',
};

const decisionConfig: Record<Decision, { bg: string; text: string; border: string }> = {
  PASS: { bg: 'rgba(34,197,94,0.15)', text: COLORS.pass, border: 'rgba(34,197,94,0.3)' },
  FAIL: { bg: 'rgba(239,68,68,0.15)', text: COLORS.fail, border: 'rgba(239,68,68,0.3)' },
  REVIEW: { bg: 'rgba(245,158,11,0.15)', text: COLORS.review, border: 'rgba(245,158,11,0.3)' },
};

export default function InspectionDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();

  const [data, setData] = useState<InspectionResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [activeView, setActiveView] = useState<'heatmap' | 'original'>('heatmap');

  useEffect(() => {
    if (!id) return;
    getInspection(id)
      .then(setData)
      .catch(() => Alert.alert('Error', 'Failed to load inspection details.'))
      .finally(() => setLoading(false));
  }, [id]);

  const handleDelete = () => {
    Alert.alert('Delete Record', 'Are you sure you want to delete this inspection record?', [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Delete',
        style: 'destructive',
        onPress: async () => {
          if (!id) return;
          try {
            await deleteInspection(id);
            router.back();
          } catch {
            Alert.alert('Error', 'Failed to delete record.');
          }
        },
      },
    ]);
  };

  if (loading) {
    return (
      <View style={styles.center}>
        <ActivityIndicator size="large" color={COLORS.accent} />
        <Text style={styles.loadingText}>Fetching inspection details...</Text>
      </View>
    );
  }

  if (!data) {
    return (
      <View style={styles.center}>
        <Text style={styles.emptyTitle}>Inspection Not Found</Text>
        <TouchableOpacity style={styles.backBtn} onPress={() => router.back()}>
          <Text style={styles.backBtnText}>Return to History</Text>
        </TouchableOpacity>
      </View>
    );
  }

  const dStyle = decisionConfig[data.decision] || decisionConfig.REVIEW;
  const displayImageUri =
    activeView === 'heatmap' && data.heatmap_url
      ? data.heatmap_url
      : data.original_image_url || data.heatmap_url;

  return (
    <SafeAreaView edges={['bottom']} style={styles.container}>
      {/* Top Header */}
      <View style={styles.header}>
        <TouchableOpacity onPress={() => router.back()} style={styles.navBtn}>
          <Text style={styles.navBtnText}>← Back</Text>
        </TouchableOpacity>
        <Text style={styles.headerTitle} numberOfLines={1}>
          {data.product?.name || 'Inspection Unit'}
        </Text>
        <TouchableOpacity onPress={handleDelete} style={styles.deleteBtn}>
          <Text style={styles.deleteBtnText}>Delete</Text>
        </TouchableOpacity>
      </View>

      <ScrollView contentContainerStyle={styles.scroll}>
        {/* Decision Hero Card */}
        <View style={[styles.heroCard, { borderColor: dStyle.border }]}>
          <View style={styles.heroRow}>
            <View>
              <Text style={styles.unitId}>UNIT #{data.inspection_id.slice(-8).toUpperCase()}</Text>
              <Text style={styles.productTitle}>{data.product?.name || 'Industrial Part'}</Text>
            </View>
            <View style={[styles.badge, { backgroundColor: dStyle.bg, borderColor: dStyle.border }]}>
              <Text style={[styles.badgeText, { color: dStyle.text }]}>{data.decision}</Text>
            </View>
          </View>

          <View style={styles.metricsRow}>
            <View style={styles.metric}>
              <Text style={styles.mLabel}>ANOMALY SCORE</Text>
              <Text
                style={[
                  styles.mVal,
                  { color: data.anomaly_score > data.threshold ? COLORS.fail : COLORS.pass },
                ]}
              >
                {data.anomaly_score.toFixed(3)}
              </Text>
            </View>
            <View style={styles.metric}>
              <Text style={styles.mLabel}>THRESHOLD</Text>
              <Text style={styles.mVal}>{(data.threshold * 100).toFixed(0)}%</Text>
            </View>
            <View style={styles.metric}>
              <Text style={styles.mLabel}>CONFIDENCE</Text>
              <Text style={styles.mVal}>{data.confidence === 0 ? 'Unavailable' : `${(data.confidence * 100).toFixed(0)}%`}</Text>
            </View>
            <View style={styles.metric}>
              <Text style={styles.mLabel}>LATENCY</Text>
              <Text style={styles.mVal}>{Math.round(data.processing_time_ms)}ms</Text>
            </View>
          </View>
        </View>

        {/* Visual Heatmap / Photo Viewer */}
        <View style={styles.viewerCard}>
          <View style={styles.viewToggleRow}>
            <TouchableOpacity
              style={[styles.toggleBtn, activeView === 'heatmap' && styles.toggleBtnActive]}
              onPress={() => setActiveView('heatmap')}
            >
              <Text
                style={[styles.toggleText, activeView === 'heatmap' && styles.toggleTextActive]}
              >
                Heatmap Overlay
              </Text>
            </TouchableOpacity>
            <TouchableOpacity
              style={[styles.toggleBtn, activeView === 'original' && styles.toggleBtnActive]}
              onPress={() => setActiveView('original')}
            >
              <Text
                style={[styles.toggleText, activeView === 'original' && styles.toggleTextActive]}
              >
                Original Photo
              </Text>
            </TouchableOpacity>
          </View>

          {displayImageUri ? (
            <Image
              source={{ uri: displayImageUri }}
              style={styles.inspectImage}
              resizeMode="contain"
            />
          ) : (
            <View style={styles.noImage}>
              <Text style={styles.noImageText}>Image preview unavailable</Text>
            </View>
          )}
        </View>

        {/* AI Diagnostics Summary */}
        <View style={styles.sectionCard}>
          <Text style={styles.sectionHeading}>Inspection Summary</Text>
          <Text style={styles.summaryText}>{data.summary}</Text>
        </View>

        {/* Defects List */}
        <View style={styles.sectionCard}>
          <Text style={styles.sectionHeading}>
            Detected Anomalies ({data.defects ? data.defects.length : 0})
          </Text>

          {data.defects && data.defects.length > 0 ? (
            data.defects.map((defect, i) => (
              <View key={i} style={styles.defectRow}>
                <View style={styles.defectHeader}>
                  <Text style={styles.defectType}>{defect.type}</Text>
                  <View
                    style={[
                      styles.severityBadge,
                      {
                        backgroundColor:
                          defect.severity === 'high'
                            ? 'rgba(239,68,68,0.2)'
                            : defect.severity === 'medium'
                            ? 'rgba(245,158,11,0.2)'
                            : 'rgba(59,130,246,0.2)',
                      },
                    ]}
                  >
                    <Text
                      style={[
                        styles.severityText,
                        {
                          color:
                            defect.severity === 'high'
                              ? COLORS.fail
                              : defect.severity === 'medium'
                              ? COLORS.review
                              : COLORS.accent,
                        },
                      ]}
                    >
                      {defect.severity.toUpperCase()}
                    </Text>
                  </View>
                </View>
                {defect.description && (
                  <Text style={styles.defectDesc}>{defect.description}</Text>
                )}
                {defect.region && (
                  <Text style={styles.defectRegion}>
                    Region: X:{Math.round(defect.region.x)}, Y:{Math.round(defect.region.y)} (
                    {Math.round(defect.region.width)}x{Math.round(defect.region.height)})
                  </Text>
                )}
              </View>
            ))
          ) : (
            <Text style={styles.noDefectsText}>
              No localized defects identified. Unit conforms to calibrated surface tolerances.
            </Text>
          )}
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.bg,
  },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: COLORS.surface,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  navBtn: {
    paddingVertical: 4,
    paddingHorizontal: 8,
  },
  navBtnText: {
    color: COLORS.accent,
    fontWeight: '700',
    fontSize: 14,
  },
  headerTitle: {
    fontSize: 15,
    fontWeight: '700',
    color: COLORS.text,
    maxWidth: 200,
  },
  deleteBtn: {
    paddingVertical: 4,
    paddingHorizontal: 8,
  },
  deleteBtnText: {
    color: COLORS.fail,
    fontSize: 13,
    fontWeight: '600',
  },
  scroll: {
    padding: 16,
    gap: 14,
  },
  heroCard: {
    backgroundColor: COLORS.surface,
    borderRadius: 12,
    borderWidth: 1,
    padding: 16,
  },
  heroRow: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 16,
  },
  unitId: {
    fontSize: 10,
    fontWeight: '700',
    color: COLORS.muted,
    letterSpacing: 1,
  },
  productTitle: {
    fontSize: 18,
    fontWeight: '800',
    color: COLORS.text,
    marginTop: 2,
  },
  badge: {
    paddingHorizontal: 12,
    paddingVertical: 6,
    borderRadius: 8,
    borderWidth: 1,
  },
  badgeText: {
    fontSize: 13,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
  metricsRow: {
    flexDirection: 'row',
    backgroundColor: COLORS.panel,
    borderRadius: 8,
    padding: 12,
    justifyContent: 'space-between',
  },
  metric: {
    alignItems: 'flex-start',
  },
  mLabel: {
    fontSize: 8,
    fontWeight: '700',
    color: COLORS.muted,
    letterSpacing: 0.5,
    marginBottom: 2,
  },
  mVal: {
    fontSize: 14,
    fontWeight: '800',
    color: COLORS.text,
  },
  viewerCard: {
    backgroundColor: COLORS.surface,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: COLORS.border,
    padding: 12,
  },
  viewToggleRow: {
    flexDirection: 'row',
    backgroundColor: COLORS.panel,
    borderRadius: 8,
    padding: 4,
    marginBottom: 12,
    gap: 6,
  },
  toggleBtn: {
    flex: 1,
    paddingVertical: 8,
    alignItems: 'center',
    borderRadius: 6,
  },
  toggleBtnActive: {
    backgroundColor: COLORS.accent,
  },
  toggleText: {
    fontSize: 12,
    color: COLORS.muted,
    fontWeight: '600',
  },
  toggleTextActive: {
    color: '#fff',
    fontWeight: '700',
  },
  inspectImage: {
    width: '100%',
    height: 260,
    borderRadius: 8,
    backgroundColor: '#000',
  },
  noImage: {
    height: 200,
    justifyContent: 'center',
    alignItems: 'center',
  },
  noImageText: {
    color: COLORS.muted,
    fontSize: 12,
  },
  sectionCard: {
    backgroundColor: COLORS.surface,
    borderRadius: 12,
    borderWidth: 1,
    borderColor: COLORS.border,
    padding: 16,
  },
  sectionHeading: {
    fontSize: 14,
    fontWeight: '700',
    color: COLORS.text,
    marginBottom: 8,
  },
  summaryText: {
    fontSize: 13,
    color: COLORS.text,
    lineHeight: 20,
  },
  defectRow: {
    backgroundColor: COLORS.panel,
    borderRadius: 8,
    padding: 10,
    marginBottom: 8,
  },
  defectHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    marginBottom: 4,
  },
  defectType: {
    fontSize: 13,
    fontWeight: '700',
    color: COLORS.text,
  },
  severityBadge: {
    paddingHorizontal: 8,
    paddingVertical: 2,
    borderRadius: 4,
  },
  severityText: {
    fontSize: 9,
    fontWeight: '800',
    letterSpacing: 0.5,
  },
  defectDesc: {
    fontSize: 12,
    color: COLORS.muted,
    lineHeight: 16,
    marginBottom: 4,
  },
  defectRegion: {
    fontSize: 10,
    color: COLORS.muted,
    fontFamily: 'monospace',
  },
  noDefectsText: {
    fontSize: 13,
    color: COLORS.pass,
    fontStyle: 'italic',
  },
  center: {
    flex: 1,
    backgroundColor: COLORS.bg,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 20,
  },
  loadingText: {
    marginTop: 12,
    color: COLORS.muted,
    fontSize: 13,
  },
  emptyTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.text,
    marginBottom: 12,
  },
  backBtn: {
    backgroundColor: COLORS.accent,
    paddingHorizontal: 16,
    paddingVertical: 10,
    borderRadius: 8,
  },
  backBtnText: {
    color: '#fff',
    fontWeight: '700',
    fontSize: 13,
  },
});
