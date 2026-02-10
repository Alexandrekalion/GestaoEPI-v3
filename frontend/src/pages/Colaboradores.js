import React, { useEffect, useState, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import { DashboardLayout } from '@/components/layout/DashboardLayout';
import { Plus, Search, User, Camera, Upload, Eye, Edit2, FileDown, FileUp, FileText, Loader2 } from 'lucide-react';
import axios from 'axios';
import { getAuthHeader } from '@/contexts/AuthContext';
import { toast } from 'sonner';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogTrigger } from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import Webcam from 'react-webcam';

const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
const API = `${BACKEND_URL}/api`;

// Componente de Avatar com fallback para erro de carregamento
const AvatarImage = ({ src, alt, className, fallbackClassName }) => {
  const [hasError, setHasError] = useState(false);
  
  if (hasError || !src) {
    return (
      <div className={fallbackClassName || "w-12 h-12 bg-emerald-100 rounded-full flex items-center justify-center flex-shrink-0"}>
        <User className="w-6 h-6 text-emerald-600" />
      </div>
    );
  }
  
  return (
    <img 
      src={src} 
      alt={alt || ""} 
      className={className}
      onError={() => setHasError(true)}
    />
  );
};

export default function Colaboradores() {
  const navigate = useNavigate();
  const [colaboradores, setColaboradores] = useState([]);
  const [filteredColaboradores, setFilteredColaboradores] = useState([]);
  const [empresas, setEmpresas] = useState([]);
  const [loading, setLoading] = useState(true);
  const [showDialog, setShowDialog] = useState(false);
  const [showWebcam, setShowWebcam] = useState(false);
  const [photoFile, setPhotoFile] = useState(null);
  const [photoPreview, setPhotoPreview] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [showImportDialog, setShowImportDialog] = useState(false);
  const [importFile, setImportFile] = useState(null);
  const [importing, setImporting] = useState(false);
  const [exporting, setExporting] = useState(false);
  const webcamRef = useRef(null);
  const importInputRef = useRef(null);
  const [formData, setFormData] = useState({
    full_name: '',
    cpf: '',
    rg: '',
    registration_number: '',
    company_id: '',
    position: '',
    department: '',
    status: 'active',
    facial_consent: false
  });

  useEffect(() => {
    fetchData();
  }, []);

  useEffect(() => {
    filterColaboradores();
  }, [searchTerm, colaboradores]);

  const fetchData = async () => {
    try {
      const [colRes, empRes] = await Promise.all([
        axios.get(`${API}/employees`, { headers: getAuthHeader() }),
        axios.get(`${API}/companies`, { headers: getAuthHeader() })
      ]);
      setColaboradores(colRes.data);
      setFilteredColaboradores(colRes.data);
      setEmpresas(empRes.data);
    } catch (error) {
      console.error('Erro:', error);
      toast.error('Erro ao carregar dados');
    } finally {
      setLoading(false);
    }
  };

  // Funções de importação/exportação
  const downloadTemplate = async () => {
    try {
      const response = await axios.get(`${API}/employees/template/excel`, {
        headers: getAuthHeader(),
        responseType: 'blob'
      });
      
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', 'template_colaboradores.xlsx');
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast.success('Template baixado!');
    } catch (error) {
      console.error('Erro ao baixar template:', error);
      toast.error('Erro ao baixar template');
    }
  };

  const exportToExcel = async () => {
    setExporting(true);
    try {
      const response = await axios.get(`${API}/employees/export/excel`, {
        headers: getAuthHeader(),
        responseType: 'blob'
      });
      
      const url = window.URL.createObjectURL(new Blob([response.data]));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `colaboradores_${new Date().toISOString().split('T')[0]}.xlsx`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast.success('Exportação concluída!');
    } catch (error) {
      console.error('Erro ao exportar:', error);
      toast.error('Erro ao exportar dados');
    } finally {
      setExporting(false);
    }
  };

  const exportToPDF = async () => {
    setExporting(true);
    try {
      const response = await axios.get(`${API}/reports/employees/pdf`, {
        headers: getAuthHeader(),
        responseType: 'blob'
      });
      
      const url = window.URL.createObjectURL(new Blob([response.data], { type: 'application/pdf' }));
      const link = document.createElement('a');
      link.href = url;
      link.setAttribute('download', `colaboradores_${new Date().toISOString().split('T')[0]}.pdf`);
      document.body.appendChild(link);
      link.click();
      link.remove();
      toast.success('PDF gerado!');
    } catch (error) {
      console.error('Erro ao gerar PDF:', error);
      toast.error('Erro ao gerar PDF');
    } finally {
      setExporting(false);
    }
  };

  const handleImportFile = (e) => {
    const file = e.target.files[0];
    if (file) {
      setImportFile(file);
    }
  };

  const importFromExcel = async () => {
    if (!importFile) {
      toast.error('Selecione um arquivo Excel');
      return;
    }

    setImporting(true);
    try {
      const formData = new FormData();
      formData.append('file', importFile);
      
      const response = await axios.post(`${API}/employees/import/excel`, formData, {
        headers: {
          ...getAuthHeader(),
          'Content-Type': 'multipart/form-data'
        }
      });
      
      const { imported, errors, skipped } = response.data;
      
      if (imported > 0) {
        toast.success(`${imported} colaborador(es) importado(s) com sucesso!`);
      }
      if (skipped > 0) {
        toast.warning(`${skipped} registro(s) ignorado(s) (duplicados)`);
      }
      if (errors.length > 0) {
        const errorMsg = errors.slice(0, 3).map(e => `Linha ${e.row}: ${e.errors.join(', ')}`).join('\n');
        toast.error(`Erros encontrados:\n${errorMsg}${errors.length > 3 ? `\n... e mais ${errors.length - 3} erro(s)` : ''}`);
      }
      
      setShowImportDialog(false);
      setImportFile(null);
      fetchData();
    } catch (error) {
      console.error('Erro ao importar:', error);
      toast.error(error.response?.data?.detail || 'Erro ao importar arquivo');
    } finally {
      setImporting(false);
    }
  };

  const filterColaboradores = () => {
    if (!searchTerm.trim()) {
      setFilteredColaboradores(colaboradores);
      return;
    }
    
    const term = searchTerm.toLowerCase();
    const filtered = colaboradores.filter(col => 
      col.full_name?.toLowerCase().includes(term) ||
      col.cpf?.toLowerCase().includes(term) ||
      col.registration_number?.toLowerCase().includes(term) ||
      col.department?.toLowerCase().includes(term) ||
      col.position?.toLowerCase().includes(term)
    );
    setFilteredColaboradores(filtered);
  };

  const capturePhoto = () => {
    const imageSrc = webcamRef.current.getScreenshot();
    fetch(imageSrc)
      .then(res => res.blob())
      .then(blob => {
        const file = new File([blob], 'photo.jpg', { type: 'image/jpeg' });
        setPhotoFile(file);
        setPhotoPreview(imageSrc);
        setShowWebcam(false);
        toast.success('Foto capturada!');
      });
  };

  const handleFileUpload = (e) => {
    const file = e.target.files[0];
    if (file) {
      setPhotoFile(file);
      setPhotoPreview(URL.createObjectURL(file));
      toast.success('Foto selecionada!');
    }
  };

  const handleSubmit = async (e) => {
    e.preventDefault();
    try {
      const response = await axios.post(`${API}/employees`, formData, { headers: getAuthHeader() });
      
      if (photoFile) {
        const formDataPhoto = new FormData();
        formDataPhoto.append('file', photoFile);
        await axios.post(`${API}/employees/${response.data.id}/photo`, formDataPhoto, {
          headers: { ...getAuthHeader(), 'Content-Type': 'multipart/form-data' }
        });
      }
      
      toast.success('Colaborador cadastrado com sucesso!');
      setShowDialog(false);
      resetForm();
      fetchData();
    } catch (error) {
      const errorMsg = error.response?.data?.detail || 'Erro ao cadastrar';
      toast.error(errorMsg);
    }
  };

  const resetForm = () => {
    setFormData({
      full_name: '',
      cpf: '',
      rg: '',
      registration_number: '',
      company_id: '',
      position: '',
      department: '',
      status: 'active',
      facial_consent: false
    });
    setPhotoFile(null);
    setPhotoPreview(null);
  };

  const openColaborador = (id) => {
    navigate(`/colaboradores/${id}`);
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

  return (
    <DashboardLayout>
      <div className="space-y-6" data-testid="colaboradores-page">
        <div className="flex items-center justify-between flex-wrap gap-4">
          <div>
            <h1 className="text-3xl font-bold text-slate-900 tracking-tight">Colaboradores</h1>
            <p className="text-slate-600 mt-1">Gerencie os colaboradores da empresa</p>
          </div>
          
          <div className="flex items-center gap-2 flex-wrap">
            {/* Botões de Importação/Exportação */}
            <div className="flex items-center gap-1 border border-slate-200 rounded-lg p-1 bg-slate-50">
              <Button 
                variant="ghost" 
                size="sm"
                onClick={downloadTemplate}
                className="text-slate-600 hover:text-slate-900"
                data-testid="download-template-btn"
                title="Baixar Template Excel"
              >
                <FileDown className="w-4 h-4" />
              </Button>
              <Button 
                variant="ghost" 
                size="sm"
                onClick={() => setShowImportDialog(true)}
                className="text-slate-600 hover:text-slate-900"
                data-testid="import-excel-btn"
                title="Importar Excel"
              >
                <FileUp className="w-4 h-4" />
              </Button>
              <Button 
                variant="ghost" 
                size="sm"
                onClick={exportToExcel}
                disabled={exporting}
                className="text-slate-600 hover:text-slate-900"
                data-testid="export-excel-btn"
                title="Exportar Excel"
              >
                {exporting ? <Loader2 className="w-4 h-4 animate-spin" /> : <FileDown className="w-4 h-4" />}
              </Button>
              <Button 
                variant="ghost" 
                size="sm"
                onClick={exportToPDF}
                disabled={exporting}
                className="text-slate-600 hover:text-slate-900"
                data-testid="export-pdf-btn"
                title="Exportar PDF"
              >
                <FileText className="w-4 h-4" />
              </Button>
            </div>
            
            <Dialog open={showDialog} onOpenChange={setShowDialog}>
              <DialogTrigger asChild>
                <Button className="bg-emerald-500 hover:bg-emerald-600" data-testid="add-colaborador-button">
                  <Plus className="w-4 h-4 mr-2" />
                  Novo Colaborador
                </Button>
              </DialogTrigger>
              <DialogContent className="max-w-2xl max-h-[90vh] overflow-y-auto">
                <DialogHeader>
                  <DialogTitle>Novo Colaborador</DialogTitle>
                </DialogHeader>
              <form onSubmit={handleSubmit} className="space-y-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="col-span-2">
                    <label className="block text-sm font-medium mb-1">Nome Completo *</label>
                    <input
                      type="text"
                      required
                      value={formData.full_name}
                      onChange={(e) => setFormData({...formData, full_name: e.target.value})}
                      className="flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
                      data-testid="input-full-name"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">CPF *</label>
                    <input
                      type="text"
                      required
                      value={formData.cpf}
                      onChange={(e) => setFormData({...formData, cpf: e.target.value})}
                      className="flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
                      placeholder="000.000.000-00"
                      data-testid="input-cpf"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">RG</label>
                    <input
                      type="text"
                      value={formData.rg}
                      onChange={(e) => setFormData({...formData, rg: e.target.value})}
                      className="flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Matrícula *</label>
                    <input
                      type="text"
                      required
                      value={formData.registration_number}
                      onChange={(e) => setFormData({...formData, registration_number: e.target.value})}
                      className="flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
                      data-testid="input-registration-number"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Empresa *</label>
                    <select
                      required
                      value={formData.company_id}
                      onChange={(e) => setFormData({...formData, company_id: e.target.value})}
                      className="flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
                      data-testid="input-company-id"
                    >
                      <option value="">Selecione...</option>
                      {empresas.map(emp => (
                        <option key={emp.id} value={emp.id}>{emp.legal_name}</option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Cargo</label>
                    <input
                      type="text"
                      value={formData.position}
                      onChange={(e) => setFormData({...formData, position: e.target.value})}
                      className="flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium mb-1">Setor/Departamento</label>
                    <input
                      type="text"
                      value={formData.department}
                      onChange={(e) => setFormData({...formData, department: e.target.value})}
                      className="flex h-10 w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm"
                    />
                  </div>
                </div>

                <div className="border-t pt-4">
                  <label className="block text-sm font-medium mb-2">Foto do Colaborador</label>
                  {photoPreview ? (
                    <div className="mb-3">
                      <img src={photoPreview} alt="Preview" className="w-32 h-32 rounded-lg object-cover" />
                      <button
                        type="button"
                        onClick={() => { setPhotoPreview(null); setPhotoFile(null); }}
                        className="text-sm text-red-500 mt-2"
                      >
                        Remover foto
                      </button>
                    </div>
                  ) : null}
                  
                  {!showWebcam && !photoPreview && (
                    <div className="flex flex-wrap gap-3">
                      <button
                        type="button"
                        onClick={() => setShowWebcam(true)}
                        className="flex items-center gap-2 px-4 py-2 bg-blue-500 text-white rounded-md hover:bg-blue-600"
                      >
                        <Camera className="w-4 h-4" />
                        Capturar Foto
                      </button>
                      <label className="flex items-center gap-2 px-4 py-2 bg-slate-500 text-white rounded-md hover:bg-slate-600 cursor-pointer">
                        <Upload className="w-4 h-4" />
                        Upload Foto
                        <input type="file" accept="image/*" onChange={handleFileUpload} className="hidden" />
                      </label>
                      {/* Opção para tirar foto diretamente no celular */}
                      <label className="flex items-center gap-2 px-4 py-2 bg-emerald-500 text-white rounded-md hover:bg-emerald-600 cursor-pointer sm:hidden">
                        <Camera className="w-4 h-4" />
                        Tirar Foto
                        <input 
                          type="file" 
                          accept="image/*" 
                          capture="user" 
                          onChange={handleFileUpload} 
                          className="hidden" 
                        />
                      </label>
                    </div>
                  )}

                  {showWebcam && (
                    <div>
                      <Webcam
                        ref={webcamRef}
                        audio={false}
                        screenshotFormat="image/jpeg"
                        className="w-full rounded-lg mb-3"
                        videoConstraints={{
                          facingMode: "user", // Câmera frontal no celular
                          width: { ideal: 640 },
                          height: { ideal: 480 }
                        }}
                        onUserMediaError={(error) => {
                          console.error('Erro ao acessar câmera:', error);
                          toast.error('Erro ao acessar câmera. Verifique as permissões do navegador.');
                          setShowWebcam(false);
                        }}
                      />
                      <div className="flex gap-3">
                        <button
                          type="button"
                          onClick={capturePhoto}
                          className="px-4 py-2 bg-emerald-500 text-white rounded-md hover:bg-emerald-600"
                        >
                          Capturar
                        </button>
                        <button
                          type="button"
                          onClick={() => setShowWebcam(false)}
                          className="px-4 py-2 bg-slate-200 text-slate-700 rounded-md hover:bg-slate-300"
                        >
                          Cancelar
                        </button>
                      </div>
                    </div>
                  )}
                </div>

                <div className="flex items-center gap-2">
                  <input
                    type="checkbox"
                    id="consent"
                    checked={formData.facial_consent}
                    onChange={(e) => setFormData({...formData, facial_consent: e.target.checked})}
                    className="w-4 h-4"
                  />
                  <label htmlFor="consent" className="text-sm text-slate-600">
                    Autorizo o uso de biometria facial (LGPD)
                  </label>
                </div>

                <Button type="submit" className="w-full bg-emerald-500 hover:bg-emerald-600" data-testid="submit-colaborador">
                  Cadastrar Colaborador
                </Button>
              </form>
            </DialogContent>
          </Dialog>
          </div>
        </div>

        {/* Dialog de Importação */}
        <Dialog open={showImportDialog} onOpenChange={setShowImportDialog}>
          <DialogContent className="max-w-md">
            <DialogHeader>
              <DialogTitle>Importar Colaboradores</DialogTitle>
            </DialogHeader>
            <div className="space-y-4 py-4">
              <p className="text-sm text-slate-600">
                Faça upload de um arquivo Excel (.xlsx) com os dados dos colaboradores.
                Use o template para garantir o formato correto.
              </p>
              
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={downloadTemplate}>
                  <FileDown className="w-4 h-4 mr-2" />
                  Baixar Template
                </Button>
              </div>
              
              <div className="border-2 border-dashed border-slate-200 rounded-lg p-6 text-center">
                {importFile ? (
                  <div className="space-y-2">
                    <FileText className="w-8 h-8 text-emerald-500 mx-auto" />
                    <p className="text-sm font-medium">{importFile.name}</p>
                    <Button 
                      variant="ghost" 
                      size="sm" 
                      onClick={() => setImportFile(null)}
                      className="text-red-500 hover:text-red-600"
                    >
                      Remover
                    </Button>
                  </div>
                ) : (
                  <label className="cursor-pointer">
                    <FileUp className="w-8 h-8 text-slate-400 mx-auto mb-2" />
                    <p className="text-sm text-slate-600">Clique para selecionar arquivo</p>
                    <p className="text-xs text-slate-400 mt-1">Apenas .xlsx ou .xls</p>
                    <input 
                      type="file" 
                      accept=".xlsx,.xls" 
                      onChange={handleImportFile}
                      className="hidden"
                      ref={importInputRef}
                    />
                  </label>
                )}
              </div>
              
              <div className="flex gap-2 justify-end">
                <Button variant="outline" onClick={() => { setShowImportDialog(false); setImportFile(null); }}>
                  Cancelar
                </Button>
                <Button 
                  onClick={importFromExcel} 
                  disabled={!importFile || importing}
                  className="bg-emerald-500 hover:bg-emerald-600"
                >
                  {importing ? (
                    <>
                      <Loader2 className="w-4 h-4 mr-2 animate-spin" />
                      Importando...
                    </>
                  ) : (
                    <>
                      <FileUp className="w-4 h-4 mr-2" />
                      Importar
                    </>
                  )}
                </Button>
              </div>
            </div>
          </DialogContent>
        </Dialog>

        <div className="bg-white border border-slate-200 rounded-lg shadow-sm">
          <div className="p-4 border-b border-slate-200">
            <div className="flex items-center gap-3">
              <Search className="w-5 h-5 text-slate-400" />
              <input
                type="text"
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                placeholder="Buscar por nome, CPF, matrícula, cargo, setor..."
                className="flex-1 outline-none text-sm"
                data-testid="search-colaborador"
              />
              {searchTerm && (
                <button 
                  onClick={() => setSearchTerm('')}
                  className="text-slate-400 hover:text-slate-600"
                >
                  Limpar
                </button>
              )}
            </div>
          </div>
          
          {filteredColaboradores.length === 0 ? (
            <div className="p-8 text-center">
              <User className="w-12 h-12 text-slate-300 mx-auto mb-3" />
              <p className="text-slate-500">
                {searchTerm ? 'Nenhum colaborador encontrado com esses critérios' : 'Nenhum colaborador cadastrado'}
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              {/* Versão Mobile - Cards */}
              <div className="block sm:hidden space-y-3 p-4">
                {filteredColaboradores.map((col) => (
                  <div 
                    key={col.id} 
                    className="bg-white border border-slate-200 rounded-lg p-4 shadow-sm"
                  >
                    <div className="flex items-start gap-4">
                      <AvatarImage 
                        src={col.photo_path ? `${BACKEND_URL}${col.photo_path}` : null}
                        className="w-16 h-16 rounded-full object-cover flex-shrink-0 border-2 border-slate-200"
                        fallbackClassName="w-16 h-16 bg-emerald-100 rounded-full flex items-center justify-center flex-shrink-0"
                      />
                      <div className="flex-1 min-w-0">
                        <p className="font-medium text-slate-900 text-lg truncate">{col.full_name}</p>
                        <p className="text-sm text-slate-500">{col.position || 'Sem cargo'}</p>
                        <p className="text-xs text-slate-400 font-mono mt-1">CPF: {col.cpf}</p>
                        <div className="flex items-center gap-2 mt-2">
                          <span className={`px-2 py-0.5 rounded-full text-xs font-medium ${
                            col.status === 'active'
                              ? 'bg-emerald-100 text-emerald-700'
                              : 'bg-slate-100 text-slate-600'
                          }`}>
                            {col.status === 'active' ? 'Ativo' : 'Inativo'}
                          </span>
                          {col.department && (
                            <span className="text-xs text-slate-500">{col.department}</span>
                          )}
                        </div>
                      </div>
                    </div>
                    <div className="mt-4 pt-3 border-t border-slate-100">
                      <Button 
                        size="sm" 
                        className="w-full bg-emerald-500 hover:bg-emerald-600"
                        onClick={() => openColaborador(col.id)}
                      >
                        <Eye className="w-4 h-4 mr-2" />
                        Ver Ficha Completa
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
              
              {/* Versão Desktop - Tabela */}
              <table className="w-full hidden sm:table">
                <thead className="bg-slate-50 border-b border-slate-200">
                  <tr>
                    <th className="px-4 lg:px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase">Colaborador</th>
                    <th className="px-4 lg:px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase">CPF</th>
                    <th className="px-4 lg:px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase hidden md:table-cell">Matrícula</th>
                    <th className="px-4 lg:px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase hidden lg:table-cell">Cargo</th>
                    <th className="px-4 lg:px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase hidden xl:table-cell">Setor</th>
                    <th className="px-4 lg:px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase">Status</th>
                    <th className="px-4 lg:px-6 py-3 text-left text-xs font-medium text-slate-500 uppercase">Ações</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-200">
                  {filteredColaboradores.map((col) => (
                    <tr key={col.id} className="hover:bg-slate-50">
                      <td className="px-4 lg:px-6 py-4">
                        <div className="flex items-center gap-3">
                          <AvatarImage 
                            src={col.photo_path ? `${BACKEND_URL}${col.photo_path}` : null}
                            className="w-12 h-12 rounded-full object-cover flex-shrink-0 border-2 border-slate-200"
                            fallbackClassName="w-12 h-12 bg-emerald-100 rounded-full flex items-center justify-center flex-shrink-0"
                          />
                          <div className="min-w-0">
                            <p className="font-medium text-slate-900 truncate">{col.full_name}</p>
                            <p className="text-sm text-slate-500 truncate">{col.position || col.department || '-'}</p>
                          </div>
                        </div>
                      </td>
                      <td className="px-4 lg:px-6 py-4 text-sm font-mono text-slate-900">{col.cpf}</td>
                      <td className="px-4 lg:px-6 py-4 text-sm font-mono text-slate-900 hidden md:table-cell">{col.registration_number || '-'}</td>
                      <td className="px-4 lg:px-6 py-4 text-sm text-slate-900 hidden lg:table-cell">{col.position || '-'}</td>
                      <td className="px-4 lg:px-6 py-4 text-sm text-slate-900 hidden xl:table-cell">{col.department || '-'}</td>
                      <td className="px-4 lg:px-6 py-4">
                        <span className={`px-2 py-1 rounded-full text-xs font-medium ${
                          col.status === 'active'
                            ? 'bg-emerald-100 text-emerald-700'
                            : 'bg-slate-100 text-slate-600'
                        }`}>
                          {col.status === 'active' ? 'Ativo' : 'Inativo'}
                        </span>
                      </td>
                      <td className="px-4 lg:px-6 py-4">
                        <Button 
                          size="sm" 
                          variant="outline" 
                          onClick={() => openColaborador(col.id)}
                          data-testid={`view-colaborador-${col.id}`}
                        >
                          <Eye className="w-4 h-4 mr-1" />
                          <span className="hidden lg:inline">Ver Ficha</span>
                        </Button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
