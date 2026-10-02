import React, { useState, useEffect, useCallback } from 'react';
import {
  View,
  Text,
  StyleSheet,
  FlatList,
  TouchableOpacity,
  RefreshControl,
  ActivityIndicator,
  Modal,
  TextInput,
  Alert,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { getProducts } from '../../src/api';
import { apiClient } from '../../src/api/client';
import type { Product } from '../../src/types';

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

export default function ProductsScreen() {
  const [products, setProducts] = useState<Product[]>([]);
  const [loading, setLoading] = useState(true);
  const [refreshing, setRefreshing] = useState(false);
  const [modalVisible, setModalVisible] = useState(false);
  const [name, setName] = useState('');
  const [code, setCode] = useState('');
  const [threshold, setThreshold] = useState('0.45');
  const [saving, setSaving] = useState(false);

  const fetchProducts = useCallback(async (isRefresh = false) => {
    try {
      if (isRefresh) setRefreshing(true);
      else setLoading(true);
      const data = await getProducts();
      setProducts(data);
    } catch {
      // offline fallback
    } finally {
      setLoading(false);
      setRefreshing(false);
    }
  }, []);

  useEffect(() => {
    fetchProducts();
  }, [fetchProducts]);

  const handleCreateProduct = async () => {
    if (!name.trim() || !code.trim()) {
      Alert.alert('Validation Error', 'Product name and code are required.');
      return;
    }
    const threshVal = parseFloat(threshold);
    if (isNaN(threshVal) || threshVal <= 0 || threshVal >= 1) {
      Alert.alert('Validation Error', 'Threshold must be a decimal between 0.05 and 0.95.');
      return;
    }

    try {
      setSaving(true);
      await apiClient.post('/products', {
        name: name.trim(),
        code: code.trim().toUpperCase(),
        threshold: threshVal,
      });
      setModalVisible(false);
      setName('');
      setCode('');
      setThreshold('0.45');
      fetchProducts();
    } catch {
      Alert.alert('Error', 'Failed to create product profile.');
    } finally {
      setSaving(false);
    }
  };

  const renderItem = ({ item }: { item: Product }) => (
    <View style={styles.card}>
      <View style={styles.cardHeader}>
        <View>
          <Text style={styles.productName}>{item.name}</Text>
          <Text style={styles.productCode}>SKU: {item.code}</Text>
        </View>
        <View style={styles.thresholdBadge}>
          <Text style={styles.thresholdLabel}>THRESHOLD</Text>
          <Text style={styles.thresholdValue}>{(item.threshold * 100).toFixed(0)}%</Text>
        </View>
      </View>

      <Text style={styles.productDesc} numberOfLines={2}>
        {item.description || 'Industrial production component with few-shot baseline profiles.'}
      </Text>

      <View style={styles.specsRow}>
        <View style={styles.specItem}>
          <Text style={styles.specLabel}>DETECTION MODEL</Text>
          <Text style={styles.specVal}>Few-Shot Ensemble</Text>
        </View>
        <View style={styles.specItem}>
          <Text style={styles.specLabel}>SENSITIVITY</Text>
          <Text style={styles.specVal}>
            {item.threshold < 0.4 ? 'Strict' : item.threshold > 0.6 ? 'Relaxed' : 'Balanced'}
          </Text>
        </View>
      </View>
    </View>
  );

  return (
    <SafeAreaView edges={['bottom']} style={styles.container}>
      <View style={styles.topBar}>
        <View>
          <Text style={styles.sectionTitle}>Product Profiles</Text>
          <Text style={styles.sectionSubtitle}>Calibrated parts & anomaly thresholds</Text>
        </View>
        <TouchableOpacity
          style={styles.addButton}
          onPress={() => setModalVisible(true)}
        >
          <Text style={styles.addButtonText}>+ New SKU</Text>
        </TouchableOpacity>
      </View>

      {loading && !refreshing ? (
        <View style={styles.centerContainer}>
          <ActivityIndicator size="large" color={COLORS.accent} />
          <Text style={styles.loadingText}>Loading products...</Text>
        </View>
      ) : products.length === 0 ? (
        <View style={styles.centerContainer}>
          <Text style={styles.emptyTitle}>No Product Profiles</Text>
          <Text style={styles.emptySubtitle}>
            Create your first SKU profile to assign calibrated quality thresholds.
          </Text>
        </View>
      ) : (
        <FlatList
          data={products}
          keyExtractor={(item) => item.id}
          renderItem={renderItem}
          contentContainerStyle={styles.listContent}
          refreshControl={
            <RefreshControl
              refreshing={refreshing}
              onRefresh={() => fetchProducts(true)}
              tintColor={COLORS.accent}
              colors={[COLORS.accent]}
            />
          }
        />
      )}

      {/* New Product Modal */}
      <Modal visible={modalVisible} transparent animationType="slide">
        <View style={styles.modalOverlay}>
          <View style={styles.modalContent}>
            <Text style={styles.modalTitle}>New Product SKU</Text>
            <Text style={styles.modalSubtitle}>Define quality parameters for your production line</Text>

            <Text style={styles.inputLabel}>Product Name</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g. PCB Motherboard Rev 3"
              placeholderTextColor={COLORS.muted}
              value={name}
              onChangeText={setName}
            />

            <Text style={styles.inputLabel}>SKU Code</Text>
            <TextInput
              style={styles.input}
              placeholder="e.g. PCB-V3-IND"
              placeholderTextColor={COLORS.muted}
              value={code}
              onChangeText={setCode}
              autoCapitalize="characters"
            />

            <Text style={styles.inputLabel}>Anomaly Threshold (0.10 - 0.90)</Text>
            <TextInput
              style={styles.input}
              placeholder="0.45"
              placeholderTextColor={COLORS.muted}
              value={threshold}
              onChangeText={setThreshold}
              keyboardType="decimal-pad"
            />

            <View style={styles.modalActions}>
              <TouchableOpacity
                style={styles.cancelBtn}
                onPress={() => setModalVisible(false)}
                disabled={saving}
              >
                <Text style={styles.cancelBtnText}>Cancel</Text>
              </TouchableOpacity>
              <TouchableOpacity
                style={styles.saveBtn}
                onPress={handleCreateProduct}
                disabled={saving}
              >
                {saving ? (
                  <ActivityIndicator color="#fff" size="small" />
                ) : (
                  <Text style={styles.saveBtnText}>Save SKU</Text>
                )}
              </TouchableOpacity>
            </View>
          </View>
        </View>
      </Modal>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  container: {
    flex: 1,
    backgroundColor: COLORS.bg,
  },
  topBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: 16,
    paddingVertical: 12,
    backgroundColor: COLORS.surface,
    borderBottomWidth: 1,
    borderBottomColor: COLORS.border,
  },
  sectionTitle: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.text,
  },
  sectionSubtitle: {
    fontSize: 11,
    color: COLORS.muted,
    marginTop: 2,
  },
  addButton: {
    backgroundColor: COLORS.accent,
    paddingHorizontal: 14,
    paddingVertical: 8,
    borderRadius: 8,
  },
  addButtonText: {
    color: '#fff',
    fontWeight: '700',
    fontSize: 12,
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
    padding: 16,
    marginBottom: 8,
  },
  cardHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'flex-start',
    marginBottom: 8,
  },
  productName: {
    fontSize: 16,
    fontWeight: '700',
    color: COLORS.text,
  },
  productCode: {
    fontSize: 12,
    color: COLORS.muted,
    marginTop: 2,
    fontWeight: '600',
  },
  thresholdBadge: {
    backgroundColor: COLORS.panel,
    borderRadius: 6,
    paddingHorizontal: 8,
    paddingVertical: 4,
    alignItems: 'center',
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  thresholdLabel: {
    fontSize: 8,
    fontWeight: '700',
    color: COLORS.muted,
    letterSpacing: 0.5,
  },
  thresholdValue: {
    fontSize: 13,
    fontWeight: '700',
    color: COLORS.accent,
    marginTop: 1,
  },
  productDesc: {
    fontSize: 12,
    color: COLORS.muted,
    lineHeight: 18,
    marginBottom: 12,
  },
  specsRow: {
    flexDirection: 'row',
    backgroundColor: COLORS.panel,
    borderRadius: 8,
    padding: 10,
    justifyContent: 'space-between',
  },
  specItem: {
    flex: 1,
  },
  specLabel: {
    fontSize: 9,
    fontWeight: '700',
    color: COLORS.muted,
    letterSpacing: 0.5,
    marginBottom: 2,
  },
  specVal: {
    fontSize: 12,
    fontWeight: '600',
    color: COLORS.text,
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
  },
  modalOverlay: {
    flex: 1,
    backgroundColor: 'rgba(0,0,0,0.7)',
    justifyContent: 'center',
    padding: 20,
  },
  modalContent: {
    backgroundColor: COLORS.surface,
    borderRadius: 14,
    padding: 20,
    borderWidth: 1,
    borderColor: COLORS.border,
  },
  modalTitle: {
    fontSize: 18,
    fontWeight: '700',
    color: COLORS.text,
  },
  modalSubtitle: {
    fontSize: 12,
    color: COLORS.muted,
    marginTop: 4,
    marginBottom: 16,
  },
  inputLabel: {
    fontSize: 11,
    fontWeight: '700',
    color: COLORS.muted,
    marginBottom: 6,
    letterSpacing: 0.5,
  },
  input: {
    backgroundColor: COLORS.panel,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 8,
    padding: 10,
    color: COLORS.text,
    fontSize: 14,
    marginBottom: 14,
  },
  modalActions: {
    flexDirection: 'row',
    justifyContent: 'flex-end',
    gap: 10,
    marginTop: 6,
  },
  cancelBtn: {
    paddingVertical: 10,
    paddingHorizontal: 16,
    borderRadius: 8,
    backgroundColor: COLORS.panel,
  },
  cancelBtnText: {
    color: COLORS.muted,
    fontWeight: '600',
    fontSize: 13,
  },
  saveBtn: {
    paddingVertical: 10,
    paddingHorizontal: 20,
    borderRadius: 8,
    backgroundColor: COLORS.accent,
  },
  saveBtnText: {
    color: '#fff',
    fontWeight: '700',
    fontSize: 13,
  },
});
