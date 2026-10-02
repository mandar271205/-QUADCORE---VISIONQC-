import { Tabs } from 'expo-router';
import { Camera, BarChart2, ClipboardList, Package } from 'lucide-react-native';

export default function TabLayout() {
  return (
    <Tabs
      screenOptions={{
        headerStyle: { backgroundColor: '#1a1d27' },
        headerTintColor: '#e2e8f0',
        headerTitleStyle: { fontWeight: '600', fontSize: 16 },
        tabBarStyle: {
          backgroundColor: '#1a1d27',
          borderTopColor: '#2d3348',
          paddingBottom: 4,
          height: 60,
        },
        tabBarActiveTintColor: '#3b82f6',
        tabBarInactiveTintColor: '#8b92a5',
        tabBarLabelStyle: { fontSize: 11, marginTop: -2 },
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
