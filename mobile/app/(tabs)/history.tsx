import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  Image,
} from 'react-native';
import { FlashList } from '@shopify/flash-list';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { getInspections } from '../../src/api';
import type { InspectionListItem, Decision } from '../../src/types';

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

const decisionConfig: Record<Decision, { bg: string; text: string; border: string }> = {
  PASS: { bg: 'rgba(34,197,94,0.15)', text: COLORS.pass, border: 'rgba(34,197,94,0.3)' },
  FAIL: { bg: 'rgba(239,68,68,0.15)', text: COLORS.fail, border: 'rgba(239,68,68,0.3)' },
  REVIEW: { bg: 'rgba(245,158,11,0.15)', text: COLORS.review, border: 'rgba(245,158,11,0.3)' },
};

export default function HistoryScreen() {
  const router = useRouter();
  const [items, setItems] = useState<InspectionListItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [filter, setFilter] = useState<'ALL' | Decision>('ALL');
  const [page, setPage] = useState(1);
  const [hasMore, setHasMore] = useState(true);

  const fetchItems = useCallback(async (pageNum = 1, isRefresh = false) => {
    try {
      if (isRefresh) setRefreshing(true);
      else if (pageNum === 1) setLoading(true);

      const params: { page: number; page_size: number; decision?: string } = {
        page: pageNum,
        page_size: 15,
      };
      if (filter !== 'ALL') {
        params.decision = filter;
      }

      const res = await getInspections(params);
      if (pageNum === 1) {
        setItems(res.items || []);
      } else {
        setItems((prev) => [...prev, ...(res.items || [])]);
      }
      setHasMore(pageNum < (res.total_pages || 1));
      setPage(pageNum);
    } catch {
      // offline or server fallback
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, [filter]);

  useEffect(() => {
    fetchItems(1);
  }, [fetchItems]);

  const onRefresh = () => fetchItems(1, true);

  const onEndReached = () => {
    if (!loading && hasMore) {
      fetchItems(page + 1);
    }
  };

  const renderBadge = (decision: Decision) => {
    const style = decisionConfig[decision] || decisionConfig.REVIEW;
    return (
      <View style={[styles.badge, { backgroundColor: style.bg, borderColor: style.border }]}>
        <Text style={[styles.badgeText, { color: style.text }]}>{decision}</Text>
      </View>
    );
  };

  const renderItem = ({ item }: { item: InspectionListItem }) => {
    const dateStr = item.created_at
      ? new Date(item.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })
      : '';
    const dateDay = item.created_at
      ? new Date(item.created_at).toLocaleDateString([], { month: 'short', day: 'numeric' })
      : '';

    return (
      <TouchableOpacity
        style={styles.card}
        activeOpacity={0.7}
        onPress={() => router.push(`/inspection/${item.inspection_id}`)}
      >
        <View style={styles.cardHeader}>
          <View style={styles.productRow}>
            <Text style={styles.productName}>
              {item.product?.name || 'General Product'}
            </Text>
            <Text style={styles.dateText}>{dateDay} {dateStr}</Text>
          </View>
          {renderBadge(item.decision)}
        </View>

        <View style={styles.cardBody}>
          <View style={styles.metricCol}>
            <Text style={styles.metricLabel}>ANOMALY SCORE</Text>
            <Text
              style={[
                styles.metricValue,
                { color: item.anomaly_score > item.threshold ? COLORS.fail : COLORS.pass },
              ]}
            >
              {item.anomaly_score.toFixed(3)}
            </Text>
          </View>

          <View style={styles.metricCol}>
            <Text style={styles.metricLabel}>THRESHOLD</Text>
            <Text style={styles.metricValue}>
              {(item.threshold * 100).toFixed(0)}%
            </Text>
          </View>

          <View style={styles.metricCol}>
            <Text style={styles.metricLabel}>LATENCY</Text>
            <Text style={styles.metricValue}>
              {item.processing_time_ms ? `${Math.round(item.processing_time_ms)}ms` : '—'}
            </Text>
          </View>

          {item.heatmap_url ? (
            <Image
              source={{ uri: item.heatmap_url }}
              style={styles.thumbImage}
              resizeMode="cover"
            />
          ) : null}
        </View>
      </TouchableOpacity>
    );
  };

  return (
    <SafeAreaView edges={['bottom']} style={styles.container}>
      {/* Filter Tabs */}
      <View style={styles.filterContainer}>
        {(['ALL', 'PASS', 'FAIL', 'REVIEW'] as const).map((tab) => (
          <TouchableOpacity
            key={tab}
            style={[styles.filterTab, filter === tab && styles.filterTabActive]}
            onPress={() => setFilter(tab)}
          >
            <Text
              style={[styles.filterTabText, filter === tab && styles.filterTabTextActive]}
            >
              {tab}
            </Text>
          </TouchableOpacity>
        ))}
      </View>

      {loading && !refreshing && items.length === 0 ? (
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color={COLORS.accent} />
          <Text style={styles.loadingText}>Loading inspection history...</Text>
        </View>
      ) : items.length === 0 ? (
        <View style={styles.centerContainer}>
          <Text style={styles.emptyTitle}>No inspections recorded</Text>
          <Text style={styles.emptySubtitle}>
            Perform quality scans using the Inspect tab to see logs here.
          </Text>
        </View>
      ) : (
        <View style={{ flex: 1 }}>
          <FlashList
            data={items}
            keyExtractor={(item) => item.inspection_id}
            renderItem={renderItem}
            contentContainerStyle={styles.listContent}

            refreshControl={
              <RefreshControl
                refreshing={refreshing}
                onRefresh={onRefresh}
                tintColor={COLORS.accent}
                colors={[COLORS.accent]}
              />
            }
            onEndReached={onEndReached}
            onEndReachedThreshold={0.3}
            ListFooterComponent={
              hasMore && !refreshing && items.length > 0 ? (
                <ActivityIndicator
                  size="small"
                  color={COLORS.muted}
                  style={{ paddingVertical: 16 }}
                />
              ) : null
            }
          />
        </View>
      )}
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.bg,
  },
  filterContainer: {
    flexDirection: 'row',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: COLORS.surface,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
    gap: 8,
  },
  filterTab: {
    flex: 1,
    paddingVertical: 8,
    borderRadius: 6,
    alignItems: 'center',
    backgroundColor: COLORS.panel,
  },
  filterTabActive: {
    backgroundColor: COLORS.accent,
  },
  filterTabText: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.muted,
  },
  filterTabTextActive: {
    color: '#fff',
  },
  listContent: {
    padding: 16,
    gap: 12,
  },
  card: {
    backgroundColor: COLORS.surface,
    borderRadius: 10,
    borderWidth: 1,
    borderColor: COLORS.border,
    padding: 14,
    marginBottom: 8,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 12,
  },
  productRow: {
    flex: 1,
    marginRight: 8,
  },
  productName: {
    fontSize: 15,
    fontWeight: '700',
    color: COLORS.text,
  },
  dateText: {
    fontSize: 11,
    color: COLORS.muted,
    marginTop: 2,
  },
  badge: {
    paddingHorizontal: 10,
    paddingVertical: 4,
    borderRadius: 6,
    borderWidth: 1,
  },
  badgeText: {
    fontSize: 11,
    fontWeight: '700',
    letterSpacing: 0.5,
  },
  cardBody: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    backgroundColor: COLORS.panel,
    borderRadius: 8,
    padding: 10,
  },
  metricCol: {
    alignItems: 'flex-start',
  },
  metricLabel: {
    fontSize: 9,
    fontWeight: '700',
    color: COLORS.muted,
    letterSpacing: 0.5,
    marginBottom: 2,
  },
  metricValue: {
    fontSize: 13,
    fontWeight: '700',
    color: COLORS.text,
  },
  thumbImage: {
    width: 44,
    height: 44,
    borderRadius: 6,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  centerContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
    padding: 24,
  },
  loadingText: {
    marginTop: 12,
    fontSize: 13,
    color: COLORS.muted,
  },
  emptyTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.text,
  },
  emptySubtitle: {
    fontSize: 12,
    color: COLORS.muted,
    textAlign: 'center',
    marginTop: 6,
    maxWidth: 240,
  },
});
