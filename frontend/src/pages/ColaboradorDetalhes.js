import React, { useEffect, useState, useRef, useCallback } from 'react';
import { useParams, useNavigate } from 'react-router-dom';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { ArrowLeft, User, Package, AlertTriangle, Calendar, History, ScanFace, CheckCircle, Trash2, Loader2, Camera, Upload } from 'lucide-react';
import axios from 'axios';
import { getAuthHeader } from '@/contexts/AuthContext';
import { toast } from 'sonner';
import Webcam from 'react-webcam';
import * as faceapi from 'face-api.js';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Configurações otimizadas para captura rápida
const FAST_DETECTOR_OPTIONS = new faceapi.TinyFaceDetectorOptions({
  inputSize: 320,       // Menor = mais rápido para captura
  scoreThreshold: 0.6   // Maior threshold para melhor qualidade
});

export default function ColaboradorDetalhes() {
  const { id } = useParams();
  const navigate = useNavigate();
  const [colaborador, setColaborador] = useState(null);
  const [historico, setHistorico] = useState([]);
  const [itemsEmUso, setItemsEmUso] = useState([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState('resumo');
  const [uploadingPhoto, setUploadingPhoto] = useState(false);
  const photoInputRef = useRef(null);
  
  // Estados para biometria facial
  const [facialTemplates, setFacialTemplates] = useState([]);
  const [showWebcam, setShowWebcam] = useState(false);
  const [modelsLoaded, setModelsLoaded] = useState(false);
  const [capturingFace, setCapturingFace] = useState(false);
  const [faceDetected, setFaceDetected] = useState(false);
  const [captureStatus, setCaptureStatus] = useState('');
  const webcamRef = useRef(null);
  const detectionIntervalRef = useRef(null);

  useEffect(() => {
    fetchData();
    loadFaceModels();
    
    return () => {
      // Limpar intervalo ao desmontar
      if (detectionIntervalRef.current) {
        clearInterval(detectionIntervalRef.current);
      }
    };
  }, [id]);
  
  // Detecção contínua de rosto para feedback em tempo real
  useEffect(() => {
    if (showWebcam && modelsLoaded && webcamRef.current) {
      detectionIntervalRef.current = setInterval(async () => {
        if (webcamRef.current && !capturingFace) {
          try {
            const imageSrc = webcamRef.current.getScreenshot();
            if (imageSrc) {
              const img = await faceapi.fetchImage(imageSrc);
              const detection = await faceapi.detectSingleFace(img, FAST_DETECTOR_OPTIONS);
              setFaceDetected(!!detection && detection.score > 0.6);
            }
          } catch (e) {
            // Ignorar erros silenciosos durante detecção contínua
          }
        }
      }, 500); // Verificar a cada 500ms
    } else {
      if (detectionIntervalRef.current) {
        clearInterval(detectionIntervalRef.current);
      }
    }
    
    return () => {
      if (detectionIntervalRef.current) {
        clearInterval(detectionIntervalRef.current);
      }
    };
  }, [showWebcam, modelsLoaded, capturingFace]);
  
  const loadFaceModels = useCallback(async () => {
    try {
      await Promise.all([
        faceapi.nets.tinyFaceDetector.loadFromUri('/models'),
        faceapi.nets.faceLandmark68Net.loadFromUri('/models'),
        faceapi.nets.faceRecognitionNet.loadFromUri('/models')
      ]);
      setModelsLoaded(true);
    } catch (error) {
      console.error('Erro ao carregar modelos faciais:', error);
    }
  }, []);
  
  const fetchFacialTemplates = async () => {
    try {
      const res = await axios.get(`${API}/employees/${id}/facial-templates`, { headers: getAuthHeader() });
      setFacialTemplates(res.data);
    } catch (error) {
      console.error('Erro ao buscar templates:', error);
    }
  };

  const fetchData = async () => {
    try {
      const [colabRes, deliveriesRes, templatesRes] = await Promise.all([
        axios.get(`${API}/employees/${id}`, { headers: getAuthHeader() }),
        axios.get(`${API}/deliveries?employee_id=${id}`, { headers: getAuthHeader() }),
        axios.get(`${API}/employees/${id}/facial-templates`, { headers: getAuthHeader() }).catch(() => ({ data: [] }))
      ]);
      
      setColaborador(colabRes.data);
      setHistorico(deliveriesRes.data);
      setFacialTemplates(templatesRes.data);
      
      // Calcular itens em uso
      const itemsMap = {};
      deliveriesRes.data.forEach(delivery => {
        if (delivery.items) {
          delivery.items.forEach(item => {
            const key = item.epi_id || item.tool_id || item.name;
            const name = item.epi_name || item.tool_name || item.name;
            if (!itemsMap[key]) {
              itemsMap[key] = { 
                name, 
                quantity: 0, 
                lastDelivery: null,
                epiData: item
              };
            }
            if (delivery.is_return) {
              itemsMap[key].quantity -= item.quantity;
            } else {
              itemsMap[key].quantity += item.quantity;
              itemsMap[key].lastDelivery = delivery.created_at;
            }
          });
        }
      });
      
      const items = Object.entries(itemsMap)
        .filter(([_, v]) => v.quantity > 0)
        .map(([id, v]) => ({ id, ...v }));
      setItemsEmUso(items);
      
    } catch (error) {
      console.error('Erro ao carregar dados:', error);
      toast.error('Erro ao carregar dados do colaborador');
    } finally {
      setLoading(false);
    }
  };

  const isNearExpiry = (date) => {
    if (!date) return false;
    const expiryDate = new Date(date);
    const now = new Date();
    const daysUntilExpiry = Math.ceil((expiryDate - now) / (1000 * 60 * 60 * 24));
    return daysUntilExpiry <= 30 && daysUntilExpiry > 0;
  };

  const isExpired = (date) => {
    if (!date) return false;
    return new Date(date) < new Date();
  };
  
  // Função otimizada de captura - RÁPIDA e com feedback
  const captureFacialTemplate = async () => {
    if (!webcamRef.current || !modelsLoaded) {
      toast.error('Câmera ou modelos não carregados');
      return;
    }
    
    if (!faceDetected) {
      toast.error('Posicione o rosto na área verde antes de capturar');
      return;
    }
    
    setCapturingFace(true);
    setCaptureStatus('Capturando imagem...');
    
    try {
      // Capturar screenshot de alta qualidade
      const imageSrc = webcamRef.current.getScreenshot();
      if (!imageSrc) {
        toast.error('Não foi possível capturar a imagem da câmera');
        setCapturingFace(false);
        setCaptureStatus('');
        return;
      }
      
      setCaptureStatus('Processando imagem...');
      
      // Criar imagem a partir do base64
      const img = new Image();
      img.crossOrigin = 'anonymous';
      
      await new Promise((resolve, reject) => {
        img.onload = resolve;
        img.onerror = reject;
        img.src = imageSrc;
      });
      
      setCaptureStatus('Detectando face...');
      
      // Usar configuração otimizada para detecção
      const detectorOptions = new faceapi.TinyFaceDetectorOptions({
        inputSize: 608,  // Maior resolução para melhor qualidade
        scoreThreshold: 0.4  // Threshold mais baixo para captura
      });
      
      const detection = await faceapi
        .detectSingleFace(img, detectorOptions)
        .withFaceLandmarks()
        .withFaceDescriptor();
      
      if (!detection) {
        toast.error('Rosto não detectado. Certifique-se de que o rosto está bem iluminado e centralizado.');
        setCapturingFace(false);
        setCaptureStatus('');
        return;
      }
      
      // Log para debug
      console.log('Detecção:', {
        score: detection.detection.score,
        landmarks: detection.landmarks.positions.length,
        descriptor: detection.descriptor.length
      });
      
      // Verificar qualidade mínima
      if (detection.detection.score < 0.5) {
        toast.error(`Qualidade baixa (${Math.round(detection.detection.score * 100)}%). Melhore a iluminação e tente novamente.`);
        setCapturingFace(false);
        setCaptureStatus('');
        return;
      }
      
      setCaptureStatus('Salvando template...');
      
      // Salvar o descriptor como template facial
      const descriptorArray = Array.from(detection.descriptor);
      
      const response = await axios.post(
        `${API}/employees/${id}/facial-templates`,
        { descriptor: JSON.stringify(descriptorArray) },
        { headers: getAuthHeader() }
      );
      
      if (response.status === 200 || response.status === 201) {
        toast.success(`✓ Template facial cadastrado! (Qualidade: ${Math.round(detection.detection.score * 100)}%)`);
        setShowWebcam(false);
        setFaceDetected(false);
        fetchFacialTemplates();
      }
    } catch (error) {
      console.error('Erro ao processar facial:', error);
      if (error.response?.data?.detail) {
        toast.error(`Erro: ${error.response.data.detail}`);
      } else if (error.message) {
        toast.error(`Erro: ${error.message}`);
      } else {
        toast.error('Erro ao processar reconhecimento facial. Tente novamente.');
      }
    } finally {
      setCapturingFace(false);
      setCaptureStatus('');
    }
  };
  
  const deleteFacialTemplate = async (templateId) => {
    if (!window.confirm('Tem certeza que deseja excluir este template facial?')) return;
    
    try {
      await axios.delete(`${API}/employees/${id}/facial-templates/${templateId}`, { headers: getAuthHeader() });
      toast.success('Template excluído');
      fetchFacialTemplates();
    } catch (error) {
      toast.error('Erro ao excluir template');
    }
  };
  
  // Upload de foto do colaborador
  const handlePhotoUpload = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    
    // Validar tipo de arquivo
    if (!file.type.startsWith('image/')) {
      toast.error('Por favor, selecione uma imagem válida');
      return;
    }
    
    // Validar tamanho (máx 5MB)
    if (file.size > 5 * 1024 * 1024) {
      toast.error('A imagem deve ter no máximo 5MB');
      return;
    }
    
    setUploadingPhoto(true);
    
    try {
      const formData = new FormData();
      formData.append('file', file);
      
      await axios.post(
        `${API}/employees/${id}/photo`,
        formData,
        { 
          headers: { 
            ...getAuthHeader(),
            'Content-Type': 'multipart/form-data'
          } 
        }
      );
      
      toast.success('Foto do colaborador atualizada com sucesso!');
      fetchData(); // Recarregar dados para mostrar nova foto
    } catch (error) {
      console.error('Erro ao fazer upload:', error);
      toast.error('Erro ao fazer upload da foto. Tente novamente.');
    } finally {
      setUploadingPhoto(false);
      if (photoInputRef.current) {
        photoInputRef.current.value = '';
      }
    }
  };

  if (loading) {
    return (
      <DashboardLayout>
        <div className="flex justify-center py-12">
          <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-emerald-500"></div>
        </div>
      </DashboardLayout>
    );
  }

  if (!colaborador) {
    return (
      <DashboardLayout>
        <div className="text-center py-12">
          <p className="text-slate-600">Colaborador não encontrado</p>
          <button onClick={() => navigate('/colaboradores')} className="mt-4 text-emerald-600 hover:underline">
            Voltar para lista
          </button>
        </div>
      </DashboardLayout>
    );
  }

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="colaborador-detalhes-page">
        {/* Header */}
        <div className="flex items-center gap-4">
          <button
            onClick={() => navigate('/colaboradores')}
            className="p-2 hover:bg-slate-100 rounded-lg transition-colors"
          >
            <ArrowLeft className="w-5 h-5 text-slate-600" />
          </button>
          <div>
            <h1 className="text-3xl font-bold text-slate-900 tracking-tight">Ficha do Colaborador</h1>
            <p className="text-slate-600 mt-1">Detalhes e histórico completo</p>
          </div>
        </div>

        {/* Informações do Colaborador */}
        <div className="bg-white border border-slate-200 rounded-lg shadow-sm p-6">
          <div className="flex items-start gap-6">
            {colaborador.photo_path ? (
              <img 
                src={`${BACKEND_URL}${colaborador.photo_path}`}
                alt={colaborador.full_name}
                className="w-32 h-32 rounded-xl object-cover border-4 border-slate-100 shadow-md"
              />
            ) : (
              <div className="w-32 h-32 bg-emerald-100 rounded-xl flex items-center justify-center border-4 border-slate-100 shadow-md">
                <User className="w-16 h-16 text-emerald-600" />
              </div>
            )}
            <div className="flex-1">
              <h2 className="text-2xl font-bold text-slate-900">{colaborador.full_name}</h2>
              <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-4">
                <div>
                  <p className="text-xs text-slate-500 uppercase">CPF</p>
                  <p className="font-mono text-slate-900">{colaborador.cpf}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 uppercase">RG</p>
                  <p className="text-slate-900">{colaborador.rg || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 uppercase">Matrícula</p>
                  <p className="font-mono text-slate-900">{colaborador.registration_number || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 uppercase">Status</p>
                  <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                    colaborador.status === 'active'
                      ? 'bg-emerald-100 text-emerald-700'
                      : 'bg-slate-100 text-slate-600'
                  }`}>
                    {colaborador.status === 'active' ? 'Ativo' : 'Inativo'}
                  </span>
                </div>
                <div>
                  <p className="text-xs text-slate-500 uppercase">Cargo</p>
                  <p className="text-slate-900">{colaborador.position || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 uppercase">Setor</p>
                  <p className="text-slate-900">{colaborador.department || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 uppercase">Telefone</p>
                  <p className="text-slate-900">{colaborador.phone || '-'}</p>
                </div>
                <div>
                  <p className="text-xs text-slate-500 uppercase">Email</p>
                  <p className="text-slate-900">{colaborador.email || '-'}</p>
                </div>
              </div>
            </div>
          </div>
        </div>

        {/* Tabs */}
        <div className="flex gap-2 border-b border-slate-200 overflow-x-auto">
          <button
            onClick={() => setActiveTab('resumo')}
            className={`px-4 py-2 font-medium text-sm border-b-2 transition-colors whitespace-nowrap ${
              activeTab === 'resumo'
                ? 'border-emerald-500 text-emerald-600'
                : 'border-transparent text-slate-600 hover:text-slate-900'
            }`}
          >
            <Package className="w-4 h-4 inline mr-2" />
            EPIs em Uso
          </button>
          <button
            onClick={() => setActiveTab('biometria')}
            className={`px-4 py-2 font-medium text-sm border-b-2 transition-colors whitespace-nowrap ${
              activeTab === 'biometria'
                ? 'border-emerald-500 text-emerald-600'
                : 'border-transparent text-slate-600 hover:text-slate-900'
            }`}
            data-testid="tab-biometria"
          >
            <ScanFace className="w-4 h-4 inline mr-2" />
            Biometria Facial
            {facialTemplates.length > 0 && (
              <span className="ml-2 px-2 py-0.5 bg-emerald-100 text-emerald-700 text-xs rounded-full">
                {facialTemplates.length}
              </span>
            )}
          </button>
          <button
            onClick={() => setActiveTab('historico')}
            className={`px-4 py-2 font-medium text-sm border-b-2 transition-colors whitespace-nowrap ${
              activeTab === 'historico'
                ? 'border-emerald-500 text-emerald-600'
                : 'border-transparent text-slate-600 hover:text-slate-900'
            }`}
          >
            <History className="w-4 h-4 inline mr-2" />
            Histórico Completo
          </button>
        </div>

        {/* EPIs em Uso */}
        {activeTab === 'resumo' && (
          <div className="bg-white border border-slate-200 rounded-lg shadow-sm p-6">
            <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
              <Package className="w-5 h-5 text-emerald-600" />
              EPIs Atualmente com o Colaborador
            </h3>
            
            {itemsEmUso.length === 0 ? (
              <p className="text-slate-500 text-center py-8">Nenhum EPI em posse do colaborador</p>
            ) : (
              <div className="space-y-3">
                {itemsEmUso.map((item, idx) => (
                  <div 
                    key={idx} 
                    className={`flex items-center justify-between p-4 rounded-lg border ${
                      isExpired(item.epiData?.validity_date) 
                        ? 'bg-red-50 border-red-200' 
                        : isNearExpiry(item.epiData?.validity_date)
                        ? 'bg-amber-50 border-amber-200'
                        : 'bg-slate-50 border-slate-200'
                    }`}
                  >
                    <div className="flex items-center gap-3">
                      <div className={`w-10 h-10 rounded-lg flex items-center justify-center ${
                        isExpired(item.epiData?.validity_date) 
                          ? 'bg-red-100' 
                          : isNearExpiry(item.epiData?.validity_date)
                          ? 'bg-amber-100'
                          : 'bg-emerald-100'
                      }`}>
                        <Package className={`w-5 h-5 ${
                          isExpired(item.epiData?.validity_date) 
                            ? 'text-red-600' 
                            : isNearExpiry(item.epiData?.validity_date)
                            ? 'text-amber-600'
                            : 'text-emerald-600'
                        }`} />
                      </div>
                      <div>
                        <p className="font-medium text-slate-900">{item.name}</p>
                        <p className="text-sm text-slate-600">
                          Entregue em: {item.lastDelivery ? new Date(item.lastDelivery).toLocaleDateString('pt-BR') : '-'}
                        </p>
                      </div>
                    </div>
                    <div className="flex items-center gap-4">
                      {(isExpired(item.epiData?.validity_date) || isNearExpiry(item.epiData?.validity_date)) && (
                        <div className="flex items-center gap-1">
                          <AlertTriangle className={`w-4 h-4 ${isExpired(item.epiData?.validity_date) ? 'text-red-500' : 'text-amber-500'}`} />
                          <span className={`text-sm font-medium ${isExpired(item.epiData?.validity_date) ? 'text-red-600' : 'text-amber-600'}`}>
                            {isExpired(item.epiData?.validity_date) ? 'Vencido' : 'Próximo do vencimento'}
                          </span>
                        </div>
                      )}
                      <span className="text-sm font-medium text-slate-700 bg-slate-200 px-3 py-1 rounded-full">
                        Qtd: {item.quantity}
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
        
        {/* Biometria Facial */}
        {activeTab === 'biometria' && (
          <div className="bg-white border border-slate-200 rounded-lg shadow-sm p-6">
            <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
              <ScanFace className="w-5 h-5 text-blue-600" />
              Cadastro de Biometria Facial
            </h3>
            
            {/* Seção de Foto do Colaborador */}
            <div className="mb-6 p-4 bg-slate-50 border border-slate-200 rounded-lg">
              <h4 className="font-medium text-slate-700 mb-3 flex items-center gap-2">
                <User className="w-4 h-4" />
                Foto do Colaborador
              </h4>
              
              <div className="flex flex-col sm:flex-row items-start gap-6">
                {/* Foto atual */}
                <div className="flex-shrink-0">
                  {colaborador.photo_path ? (
                    <img 
                      src={`${BACKEND_URL}${colaborador.photo_path}?t=${Date.now()}`}
                      alt={colaborador.full_name}
                      className="w-32 h-32 rounded-xl object-cover border-2 border-emerald-300 shadow-md"
                      onError={(e) => {
                        e.target.style.display = 'none';
                        e.target.nextSibling.style.display = 'flex';
                      }}
                    />
                  ) : null}
                  <div 
                    className={`w-32 h-32 bg-slate-200 rounded-xl flex-col items-center justify-center border-2 border-dashed border-slate-300 ${colaborador.photo_path ? 'hidden' : 'flex'}`}
                  >
                    <User className="w-12 h-12 text-slate-400" />
                    <span className="text-xs text-slate-500 mt-1">Sem foto</span>
                  </div>
                </div>
                
                {/* Upload de foto */}
                <div className="flex-1">
                  <p className="text-sm text-slate-600 mb-3">
                    {colaborador.photo_path 
                      ? 'A foto é utilizada para identificação visual do colaborador. Você pode atualizar a foto a qualquer momento.'
                      : 'Nenhuma foto cadastrada. Cadastre uma foto para permitir o reconhecimento facial.'
                    }
                  </p>
                  
                  <input
                    ref={photoInputRef}
                    type="file"
                    accept="image/*"
                    onChange={handlePhotoUpload}
                    className="hidden"
                    id="photo-upload"
                  />
                  
                  {/* Webcam para tirar foto */}
                  {showPhotoWebcam ? (
                    <div className="mb-4">
                      <Webcam
                        ref={photoWebcamRef}
                        audio={false}
                        screenshotFormat="image/jpeg"
                        className="w-full max-w-md rounded-lg border-2 border-blue-300"
                        videoConstraints={{
                          facingMode: "user",
                          width: { ideal: 640 },
                          height: { ideal: 480 }
                        }}
                        onUserMediaError={() => {
                          toast.error('Erro ao acessar câmera');
                          setShowPhotoWebcam(false);
                        }}
                      />
                      <div className="flex gap-2 mt-3">
                        <button
                          onClick={capturePhotoFromWebcam}
                          disabled={uploadingPhoto}
                          className="bg-emerald-500 hover:bg-emerald-600 text-white font-medium rounded-lg px-4 py-2 flex items-center gap-2"
                        >
                          <Camera className="w-4 h-4" />
                          Tirar Foto
                        </button>
                        <button
                          onClick={() => setShowPhotoWebcam(false)}
                          className="bg-slate-200 hover:bg-slate-300 text-slate-700 font-medium rounded-lg px-4 py-2"
                        >
                          Cancelar
                        </button>
                      </div>
                    </div>
                  ) : (
                    <div className="flex flex-wrap gap-2">
                      <button
                        onClick={() => setShowPhotoWebcam(true)}
                        disabled={uploadingPhoto}
                        className="bg-emerald-500 hover:bg-emerald-600 text-white font-medium rounded-lg px-4 py-2.5 flex items-center gap-2 transition-colors disabled:opacity-50"
                        data-testid="capture-photo-btn"
                      >
                        <Camera className="w-4 h-4" />
                        Tirar Foto
                      </button>
                      
                      <button
                        onClick={() => photoInputRef.current?.click()}
                        disabled={uploadingPhoto}
                        className="bg-blue-500 hover:bg-blue-600 text-white font-medium rounded-lg px-4 py-2.5 flex items-center gap-2 transition-colors disabled:opacity-50"
                        data-testid="upload-photo-btn"
                      >
                        {uploadingPhoto ? (
                          <>
                            <Loader2 className="w-4 h-4 animate-spin" />
                            Enviando...
                          </>
                        ) : (
                          <>
                            <Upload className="w-4 h-4" />
                            Selecionar da Galeria
                          </>
                        )}
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
            
            {/* Alerta se não tem foto */}
            {!colaborador.photo_path && (
              <div className="p-4 bg-amber-50 border border-amber-200 rounded-lg mb-6">
                <div className="flex items-start gap-3">
                  <AlertTriangle className="w-5 h-5 text-amber-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="font-medium text-amber-800">Foto não cadastrada</p>
                    <p className="text-sm text-amber-700">Cadastre uma foto acima antes de cadastrar o template facial para o reconhecimento biométrico.</p>
                  </div>
                </div>
              </div>
            )}
            
            {/* Templates cadastrados */}
            <div className="mb-6">
              <h4 className="font-medium text-slate-700 mb-2">Templates Faciais Cadastrados</h4>
              <p className="text-sm text-slate-500 mb-4">
                O template facial é uma representação matemática das características do rosto do colaborador (128 pontos de referência). 
                Ele é usado para comparar com rostos capturados pela câmera durante a entrega de EPI, permitindo a identificação automática.
              </p>
              {facialTemplates.length === 0 ? (
                <div className="p-6 bg-slate-50 border border-slate-200 rounded-lg text-center">
                  <ScanFace className="w-12 h-12 text-slate-300 mx-auto mb-3" />
                  <p className="text-slate-500">Nenhum template facial cadastrado</p>
                  <p className="text-sm text-slate-400 mt-1">Cadastre ao menos um template para habilitar o reconhecimento facial</p>
                </div>
              ) : (
                <div className="space-y-2">
                  {facialTemplates.map((template, idx) => (
                    <div 
                      key={template.id} 
                      className="flex items-center justify-between p-4 bg-emerald-50 border border-emerald-200 rounded-lg"
                    >
                      <div className="flex items-center gap-3">
                        <div className="w-10 h-10 bg-emerald-100 rounded-full flex items-center justify-center">
                          <CheckCircle className="w-5 h-5 text-emerald-600" />
                        </div>
                        <div>
                          <p className="font-medium text-slate-900">Template Facial #{idx + 1}</p>
                          <p className="text-sm text-slate-600">
                            Cadastrado em: {new Date(template.created_at).toLocaleString('pt-BR')}
                          </p>
                        </div>
                      </div>
                      <button
                        onClick={() => deleteFacialTemplate(template.id)}
                        className="p-2 text-red-500 hover:bg-red-50 rounded-lg transition-colors"
                        title="Excluir template"
                      >
                        <Trash2 className="w-5 h-5" />
                      </button>
                    </div>
                  ))}
                </div>
              )}
            </div>
            
            {/* Captura de novo template */}
            <div className="border-t pt-6">
              <h4 className="font-medium text-slate-700 mb-3">Cadastrar Novo Template via Câmera</h4>
              
              {!colaborador.photo_path ? (
                <div className="p-4 bg-slate-100 rounded-lg text-center">
                  <p className="text-slate-600">Cadastre uma foto do colaborador primeiro para poder capturar o template facial.</p>
                </div>
              ) : !modelsLoaded ? (
                <div className="flex items-center justify-center py-8">
                  <Loader2 className="w-8 h-8 animate-spin text-blue-500 mr-3" />
                  <span className="text-slate-600">Carregando modelos de reconhecimento...</span>
                </div>
              ) : !showWebcam ? (
                <button
                  onClick={() => setShowWebcam(true)}
                  className="w-full bg-blue-500 hover:bg-blue-600 text-white font-medium rounded-lg px-4 py-4 flex items-center justify-center gap-2 transition-colors"
                  data-testid="start-facial-capture"
                >
                  <Camera className="w-5 h-5" />
                  Iniciar Captura Facial
                </button>
              ) : (
                <div className="space-y-4">
                  {/* Status da detecção */}
                  <div className={`flex items-center gap-2 px-4 py-2 rounded-lg transition-colors ${
                    faceDetected 
                      ? 'bg-emerald-50 border border-emerald-200' 
                      : 'bg-amber-50 border border-amber-200'
                  }`}>
                    {faceDetected ? (
                      <>
                        <CheckCircle className="w-5 h-5 text-emerald-600" />
                        <span className="text-sm font-medium text-emerald-700">
                          Rosto detectado - Pronto para capturar!
                        </span>
                      </>
                    ) : (
                      <>
                        <ScanFace className="w-5 h-5 text-amber-600" />
                        <span className="text-sm font-medium text-amber-700">
                          Posicione o rosto na área marcada...
                        </span>
                      </>
                    )}
                  </div>
                  
                  {/* Webcam com feedback visual - ÁREA AMPLIADA */}
                  <div className="relative bg-slate-900 rounded-xl p-2">
                    <Webcam
                      ref={webcamRef}
                      audio={false}
                      screenshotFormat="image/jpeg"
                      screenshotQuality={0.95}
                      className={`w-full rounded-lg border-4 transition-colors ${
                        faceDetected ? 'border-emerald-400' : 'border-amber-300'
                      }`}
                      style={{ minHeight: '400px' }}
                      videoConstraints={{
                        facingMode: "user",
                        width: { ideal: 1280 },
                        height: { ideal: 960 },
                        frameRate: { ideal: 30 }
                      }}
                      mirrored={true}
                    />
                    {/* Guia de posicionamento - ÁREA MAIOR */}
                    <div className="absolute inset-0 flex items-center justify-center pointer-events-none p-2">
                      <div className={`w-64 h-80 border-4 border-dashed rounded-3xl transition-colors ${
                        faceDetected ? 'border-emerald-500 opacity-90' : 'border-amber-400 opacity-70'
                      }`}>
                        {/* Marcadores de canto para melhor visualização */}
                        <div className="absolute -top-1 -left-1 w-6 h-6 border-t-4 border-l-4 rounded-tl-lg border-current"></div>
                        <div className="absolute -top-1 -right-1 w-6 h-6 border-t-4 border-r-4 rounded-tr-lg border-current"></div>
                        <div className="absolute -bottom-1 -left-1 w-6 h-6 border-b-4 border-l-4 rounded-bl-lg border-current"></div>
                        <div className="absolute -bottom-1 -right-1 w-6 h-6 border-b-4 border-r-4 rounded-br-lg border-current"></div>
                      </div>
                    </div>
                    
                    {/* Status de processamento */}
                    {captureStatus && (
                      <div className="absolute inset-0 bg-black/60 flex items-center justify-center rounded-xl">
                        <div className="bg-white px-8 py-5 rounded-xl flex items-center gap-4 shadow-lg">
                          <Loader2 className="w-8 h-8 animate-spin text-blue-500" />
                          <span className="font-medium text-lg text-slate-700">{captureStatus}</span>
                        </div>
                      </div>
                    )}
                  </div>
                  
                  {/* Dicas */}
                  <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg">
                    <p className="text-xs text-slate-600">
                      <strong>Dicas:</strong> Boa iluminação frontal • Olhe para a câmera • Rosto centralizado • Sem óculos escuros
                    </p>
                  </div>
                  
                  {/* Botões de ação */}
                  <div className="flex gap-3">
                    <button
                      onClick={captureFacialTemplate}
                      disabled={capturingFace || !faceDetected}
                      className={`flex-1 font-medium rounded-lg px-4 py-3 flex items-center justify-center gap-2 transition-all ${
                        faceDetected && !capturingFace
                          ? 'bg-emerald-500 hover:bg-emerald-600 text-white'
                          : 'bg-slate-300 text-slate-500 cursor-not-allowed'
                      }`}
                      data-testid="capture-facial-button"
                    >
                      {capturingFace ? (
                        <>
                          <Loader2 className="w-5 h-5 animate-spin" />
                          Processando...
                        </>
                      ) : (
                        <>
                          <Camera className="w-5 h-5" />
                          {faceDetected ? 'Capturar Agora' : 'Aguardando rosto...'}
                        </>
                      )}
                    </button>
                    <button
                      onClick={() => {
                        setShowWebcam(false);
                        setFaceDetected(false);
                      }}
                      className="bg-slate-200 hover:bg-slate-300 text-slate-700 font-medium rounded-lg px-6 py-3 transition-colors"
                    >
                      Cancelar
                    </button>
                  </div>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Histórico Completo */}
        {activeTab === 'historico' && (
          <div className="bg-white border border-slate-200 rounded-lg shadow-sm p-6">
            <h3 className="text-lg font-bold text-slate-900 mb-4 flex items-center gap-2">
              <History className="w-5 h-5 text-emerald-600" />
              Histórico de Movimentações
            </h3>
            
            {historico.length === 0 ? (
              <p className="text-slate-500 text-center py-8">Nenhuma movimentação registrada</p>
            ) : (
              <div className="space-y-4">
                {historico.map((delivery, idx) => (
                  <div 
                    key={idx} 
                    className={`p-4 rounded-lg border ${
                      delivery.is_return 
                        ? 'bg-blue-50 border-blue-200' 
                        : 'bg-emerald-50 border-emerald-200'
                    }`}
                  >
                    <div className="flex flex-col sm:flex-row gap-4">
                      {/* Foto da Assinatura Facial */}
                      {delivery.facial_photo_path && (
                        <div className="flex-shrink-0">
                          <div className="relative">
                            <img 
                              src={`${BACKEND_URL}${delivery.facial_photo_path}`}
                              alt="Assinatura facial"
                              className="w-24 h-24 sm:w-28 sm:h-28 rounded-lg object-cover border-2 border-emerald-300 shadow-sm"
                            />
                            <div className="absolute -bottom-2 -right-2 bg-emerald-500 text-white text-xs px-2 py-0.5 rounded-full flex items-center gap-1">
                              <ScanFace className="w-3 h-3" />
                              <span>{delivery.facial_match_score ? `${(delivery.facial_match_score * 100).toFixed(0)}%` : '✓'}</span>
                            </div>
                          </div>
                          <p className="text-xs text-slate-500 text-center mt-1">Assinatura</p>
                        </div>
                      )}
                      
                      {/* Detalhes da Entrega */}
                      <div className="flex-1">
                        <div className="flex items-center justify-between mb-3">
                          <div className="flex items-center gap-3 flex-wrap">
                            <span className={`px-3 py-1 rounded-full text-xs font-medium ${
                              delivery.is_return 
                                ? 'bg-blue-200 text-blue-800' 
                                : 'bg-emerald-200 text-emerald-800'
                            }`}>
                              {delivery.is_return ? 'Devolução' : 'Entrega'}
                            </span>
                            {!delivery.facial_photo_path && delivery.facial_match_score && (
                              <span className="text-xs text-slate-500 flex items-center gap-1">
                                <ScanFace className="w-3 h-3" />
                                Verificação: {(delivery.facial_match_score * 100).toFixed(0)}%
                              </span>
                            )}
                          </div>
                          <span className="text-sm text-slate-600 flex items-center gap-1">
                            <Calendar className="w-4 h-4" />
                            {new Date(delivery.created_at).toLocaleString('pt-BR')}
                          </span>
                        </div>
                        
                        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                          {delivery.items?.map((item, i) => (
                            <div key={i} className="flex items-center gap-2 text-sm text-slate-700 bg-white/50 p-2 rounded">
                              <Package className="w-4 h-4 text-slate-400" />
                              <span className="font-medium">{item.epi_name || item.tool_name || item.name}</span>
                              <span className="text-slate-500">(Qtd: {item.quantity})</span>
                            </div>
                          ))}
                        </div>
                        
                        {delivery.delivered_by_name && (
                          <p className="text-xs text-slate-500 mt-2">
                            Responsável: {delivery.delivered_by_name}
                          </p>
                        )}
                        {delivery.notes && (
                          <p className="text-sm text-slate-600 mt-2 italic">Obs: {delivery.notes}</p>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </DashboardLayout>
  );
}
