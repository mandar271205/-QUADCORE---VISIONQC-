import { Tabs } from 'expo-router';
import { Camera, BarChart2, ClipboardList, Package } from 'lucide-react-native';

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: '#1E293B', shadowColor: 'transparent', elevation: 0 },
        headerTintColor: '#F8FAFC',
        headerTitleStyle: { fontWeight: '700', fontSize: 16, textTransform: 'uppercase', letterSpacing: 1 },
        tabBarStyle: {
          backgroundColor: '#1E293B',
          borderTopColor: '#334155',
          borderTopWidth: 1,
          paddingBottom: 4,
          height: 60,
        },
        tabBarActiveTintColor: '#06B6D4',
        tabBarInactiveTintColor: '#94A3B8',
        tabBarLabelStyle: { fontSize: 11, marginTop: -2, fontWeight: '600' },
      }}
    >
      <Tabs.Screen
        name="index"
        options={{
          title: 'Inspect',
          tabBarIcon: ({ color, size }) => <Camera color={color} size={size} />,
          headerTitle: 'VisionQC — Live Inspection',
        }}
      />
      <Tabs.Screen
        name="history"
        options={{
          title: 'History',
          tabBarIcon: ({ color, size }) => <ClipboardList color={color} size={size} />,
          headerTitle: 'Inspection History',
        }}
      />
      <Tabs.Screen
        name="products"
        options={{
          title: 'Products',
          tabBarIcon: ({ color, size }) => <Package color={color} size={size} />,
          headerTitle: 'Products',
        }}
      />
      <Tabs.Screen
        name="analytics"
        options={{
          title: 'Analytics',
          tabBarIcon: ({ color, size }) => <BarChart2 color={color} size={size} />,
          headerTitle: 'Analytics',
        }}
      />
    </Tabs>
  );
}
