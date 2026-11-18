import React from 'react';
import '../../styles/SidePanel.css';

function SidePanel({ className = '', children }) {
  return <div className={`side-panel ${className}`}>{children}</div>;
}

export default SidePanel;
