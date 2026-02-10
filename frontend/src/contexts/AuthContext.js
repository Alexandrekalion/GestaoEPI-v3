import React, { createContext, useContext, useState, useEffect } from 'react';
import axios from 'axios';

const AuthContext = createContext(null);

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

export const AuthProvider = ({ children }) => {
  const [user, setUser] = useState(null);
  const [token, setToken] = useState(localStorage.getItem('token'));
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (token) {
      fetchUser();
    } else {
      setLoading(false);
    }
  }, []);

  const fetchUser = async () => {
    const currentToken = localStorage.getItem('token');
    if (!currentToken) {
      setLoading(false);
      return;
    }
    
    try {
      const response = await axios.get(`${API}/auth/me`, {
        headers: { Authorization: `Bearer ${currentToken}` }
      });
      setUser(response.data);
      setToken(currentToken);
    } catch (error) {
      console.error('Erro ao buscar usuário:', error);
      // Token inválido, fazer logout
      localStorage.removeItem('token');
      setToken(null);
      setUser(null);
    } finally {
      setLoading(false);
    }
  };

  const login = async (username, password) => {
    // Fazer login
    const response = await axios.post(`${API}/auth/login`, { username, password });
    const { access_token, must_change_password, role } = response.data;
    
    // Verificar se o token é válido buscando dados do usuário
    if (!must_change_password) {
      try {
        const userResponse = await axios.get(`${API}/auth/me`, {
          headers: { Authorization: `Bearer ${access_token}` }
        });
        setUser(userResponse.data);
      } catch (error) {
        console.error('Erro ao buscar usuário após login:', error);
        // Se não conseguir buscar usuário, não salvar token
        throw new Error('Erro ao validar sessão. Tente novamente.');
      }
    }
    
    // Só salvar token depois de tudo OK
    localStorage.setItem('token', access_token);
    setToken(access_token);
    
    return { must_change_password, role };
  };

  const logout = () => {
    setToken(null);
    setUser(null);
    localStorage.removeItem('token');
  };

  const changePassword = async (oldPassword, newPassword) => {
    const currentToken = localStorage.getItem('token');
    await axios.post(
      `${API}/auth/change-password`,
      { old_password: oldPassword, new_password: newPassword },
      { headers: { Authorization: `Bearer ${currentToken}` } }
    );
    await fetchUser();
  };

  return (
    <AuthContext.Provider value={{ user, token, login, logout, changePassword, loading }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};

export const getAuthHeader = () => {
  const token = localStorage.getItem('token');
  return token ? { Authorization: `Bearer ${token}` } : {};
};
